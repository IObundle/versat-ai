from versatDefs import *
from versatCommons import *

import itertools

# Memory allocation is precomputed by transforming it into rectangle fitting,
# where the amount of memory is the width and the allocation time is the height and it is fixed

# TODO: How do we handle graphs that contain variable dimensions?
#       First we can separate constant size expressions and variable sized into two regions.
#       Second we should be able to generate an offset that depends on the dimension described.
# NOTE: If we find out that the size of operations is substantially different functions,
#       like one operation uses N memory while the other uses N^2 memory, then we can
#       probably solve this problem by further dividing the memory regions into one section for
#       each function type.


def CalculateGreedyMemoryAllocationOffset(memoryAllocations: list[MemoryAllocation]):
    # TODO: We are making a very simple algorithm right now. We can always improve this in the future if needed.
    #       In fact, it is preferable since if we find a problem the problematic input can help us find out how best to approach this.
    totalCycles = max([x.lastCycle for x in memoryAllocations])
    layers: list[list[int | int]] = [[] for x in range(totalCycles)]

    def GetFirstValidPointAfter(layerIndex, pointToStart):
        def Collision(point, range):
            if point >= range[0] and point < range[1]:
                return True
            return False

        layer = layers[layerIndex]
        currentPoint = pointToStart + 1
        for range in layer:
            if Collision(currentPoint, range):
                currentPoint = range[1]

        return currentPoint

    def FindCollision(layerIndex, point, size):
        layer = layers[layerIndex]
        # print(layerIndex,layer)
        for range in layer:
            if point < range[0] and point + size > range[0]:
                return range[0]
        return None

    def AddRegion(layerIndex, point, size):
        layer = layers[layerIndex]
        layer.append([point, point + size])

        # Slow
        layer = list(sorted(layer, key=lambda x: x[0]))

    if not memoryAllocations:
        return 0, []

    # Layers are just a list of ordered ranges. No point making a proper struct for such simple use case
    totalMemoryNeeded = 0
    for index, memAlloc in enumerate(memoryAllocations):
        size = memAlloc.amount

        foundFit = False
        currentPoint = -1
        while not foundFit:
            currentPoint = GetFirstValidPointAfter(memAlloc.firstCycle, currentPoint)

            canFit = True
            for layer in range(memAlloc.firstCycle, memAlloc.lastCycle):
                collisionPoint = FindCollision(layer, currentPoint, size)

                # print(index,collisionPoint,currentPoint,size)

                if collisionPoint:
                    bestValidPoint = GetFirstValidPointAfter(layer, collisionPoint)
                    canFit = False

            if canFit:
                foundFit = True
                memAlloc.offset = currentPoint
                totalMemoryNeeded = max(totalMemoryNeeded, currentPoint + size)
                for layer in range(memAlloc.firstCycle + 1, memAlloc.lastCycle):
                    AddRegion(layer, currentPoint, size)

    return totalMemoryNeeded


def CalculateMemoryAllocations(cModel):
    # Certain operators can work directly on the input memory instead of
    # having to copy everything into an output region.
    # This only works if the input is not used by anyone else meaning that
    # there are restrictions. Also only certain ops use this.
    useInplaceOptimization = True

    memoryAllocations = []
    indexesToMemoryAllocation = {}
    inplaceIndexes = []
    for c in cModel.operations:
        outputPorts = cModel.GetOutputNodesAndPortIndexes(c, 0)
        indexes = [x[0].nodeIndex for x in outputPorts]
        nodeIndex = c.nodeIndex

        if len(indexes) == 0:
            continue
        else:
            lastCycle = max(indexes)

        # In order to prevent operations that write on top of their input
        lastCycle += 1

        # If node supports inplace
        # TODO: More generic way of doing this. Need a "supportsInplace" in the operatorSpec.
        if (
            useInplaceOptimization
            and (c.opName == "Relu" or c.opName == "FixPad" or c.opName == "Reshape")
            and c.inputs[0].sourceType == DataSourceType.NODE_INPUT
        ):
            inputIndex = c.inputs[0].index

            outputs = cModel.GetOutputNodesAndPortIndexes(
                cModel.operations[inputIndex], 0
            )
            # The logic is not complete but should suffice for now.
            # We need to get more complex graphs to experiment in here
            if len(outputs) == 1:
                memoryAllocation = indexesToMemoryAllocation[inputIndex]
                memoryAllocation.lastCycle = max(memoryAllocation.lastCycle, lastCycle)

                indexesToMemoryAllocation[nodeIndex] = memoryAllocation
                inplaceIndexes.append(nodeIndex)

            continue

        # TODO: Support different tensor types and whatnot.
        memoryRequired = 16
        for dim in c.outputDimensions:
            memoryRequired *= TensorSize(dim)

        mem = MemoryAllocation(nodeIndex, lastCycle, memoryRequired)
        indexesToMemoryAllocation[nodeIndex] = mem
        memoryAllocations.append(mem)

    totalTempMemoryNeeded = 0
    if memoryAllocations:
        totalTempMemoryNeeded = CalculateGreedyMemoryAllocationOffset(memoryAllocations)

    cModel.tempMemoryNeeded = totalTempMemoryNeeded

    for mem in memoryAllocations:
        # Embedded does not support unaligned memory. Need to be very
        # carefully with all the allocations that are just passed directly
        # to the embedded this way
        assert mem.offset % 4 == 0

        op = cModel.operations[mem.firstCycle]
        op.outputMemoryAddress = MemoryLocation(mem.offset, MemoryType.TEMP)

    for index in inplaceIndexes:
        op = cModel.operations[index]
        mem = indexesToMemoryAllocation[index]
        op.outputMemoryAddress = MemoryLocation(mem.offset, MemoryType.TEMP)

    totalOutputMemory = 0
    outputOffsets = []
    for index, c in enumerate(cModel.operations):
        outputPorts = cModel.GetOutputNodesAndPortIndexes(c, 0)
        indexes = [x[0].nodeIndex for x in outputPorts]

        # Node is graph output
        if len(indexes) != 0:
            continue

        # TODO: Support different tensor types and whatnot.
        memoryRequired = 16
        for dim in c.outputDimensions:
            memoryRequired *= TensorSize(dim)

        outputOffsets.append(totalOutputMemory)
        c.outputMemoryAddress = MemoryLocation(totalOutputMemory, MemoryType.OUTPUT)
        totalOutputMemory += memoryRequired

    if 0:
        for index, c in enumerate(cModel.operations):
            print(f"Node: {c.nodeIndex}, Type: {c.opName}")
            for i, inp in enumerate(c.inputs):
                if inp.sourceType == DataSourceType.NODE_INPUT:
                    print(
                        f"  Input {i} mem {cModel.operations[inp.index].outputMemoryAddress.memType}:",
                        cModel.operations[inp.index].outputMemoryAddress.offset,
                    )

            outputSize = 1
            for dim in c.outputDimensions:
                outputSize *= TensorSize(dim)

    cModel.outputMemoryNeeded = totalOutputMemory
