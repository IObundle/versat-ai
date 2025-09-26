from versatDefs import *

import pulp  # TODO: Not sure how stable this is. Helpful for now, later we will see
import itertools


def IndexOfNodesThatUseOutput(cModel, outputName):
    indexes = []
    for index, op in enumerate(cModel.operations):
        for inp in op.inputs:
            if inp.name == outputName:
                indexes.append(index)
    return indexes


# TODO: How do we handle graphs that contain variable dimensions?
#       First we can separate constant size expressions and variable sized into two regions.
#       Second we should be able to generate an offset that depends on the dimension described.
# NOTE: If we find out that the size of operations is substantially different functions,
#       like one operation uses N memory while the other uses N^2 memory, then we can
#       probably solve this problem by further dividing the memory regions into one section for
#       each function type.


# Heavy weight algorithm to calculate the best way of performing memory allocations.
# We reduce the problem to rectangle fitting. The memory allocation is represented as rectangles where
# the width is the amount of memory used and the height is the "time" where the allocation occurs
# Each onnx operation advances time by 1 unit.
# We encode the problem as a Integer Linear program and use a solver to find the optimal solution
def CalculateOptimalMemoryAllocationOffset(memoryAllocations: list[MemoryAllocation]):
    M = 1000000  # Not a big fan of this trick. What if the memory size becomes bigger than this number? Larger M values cause the algorithm to stop working. Might depend on the solver but regardless want to see if we can find a better way.
    # TODO: Need to find an alternative

    # Create all the variables that we are gonna use
    z = {}
    r_x = [None] * len(memoryAllocations)

    for index, mem in enumerate(memoryAllocations):
        r_x[index] = pulp.LpVariable(f"r{index}_x", lowBound=0, cat="Integer")

    for memAndIndex in itertools.combinations(enumerate(memoryAllocations), 2):
        i, leftMem = memAndIndex[0]
        k, rightMem = memAndIndex[1]

        z[f"{i}_{k}_0"] = pulp.LpVariable(f"{i}_{k}_0", 0, 1, cat="Integer")
        z[f"{i}_{k}_1"] = pulp.LpVariable(f"{i}_{k}_1", 0, 1, cat="Integer")
        z[f"{i}_{k}_2"] = pulp.LpVariable(f"{i}_{k}_2", 0, 1, cat="Integer")
        z[f"{i}_{k}_3"] = pulp.LpVariable(f"{i}_{k}_3", 0, 1, cat="Integer")

    H = pulp.LpVariable("H", lowBound=0)

    prob = pulp.LpProblem("problem", pulp.LpMinimize)

    for memAndIndex in itertools.combinations(enumerate(memoryAllocations), 2):
        i, leftMem = memAndIndex[0]
        k, rightMem = memAndIndex[1]

        r0_x = r_x[i]
        r1_x = r_x[k]

        r0_w = leftMem.amount
        r1_w = rightMem.amount

        r0_y = leftMem.firstCycle
        r1_y = rightMem.firstCycle

        r0_l = leftMem.lastCycle
        r1_l = rightMem.lastCycle

        z_0 = z[f"{i}_{k}_0"]
        z_1 = z[f"{i}_{k}_1"]
        z_2 = z[f"{i}_{k}_2"]
        z_3 = z[f"{i}_{k}_3"]

        prob += r1_x + r1_w <= r0_x + M * z_0
        prob += r0_x + r0_w <= r1_x + M * z_1
        prob += r1_l <= r0_y + M * z_2
        prob += r0_l <= r1_y + M * z_3
        prob += z_0 + z_1 + z_2 + z_3 <= 3

    # Objective to minimize as a constraint in a dummy variable H
    for index, mem in enumerate(memoryAllocations):
        x = r_x[index]
        w = mem.amount
        prob += x + w <= H

    # True objective
    prob += H

    status = prob.solve(pulp.PULP_CBC_CMD(msg=0))

    # TODO: Can this occur?
    if not status:
        print("Problem calculating the optimal memory allocations")
        return None

    offsets = []
    for x in r_x:
        offsets.append(int(pulp.value(x)))

    totalMemoryNeeded = int(pulp.value(H))

    return totalMemoryNeeded, offsets


def CalculateMemoryAllocations(cModel):
    memoryAllocations = []
    for index, c in enumerate(cModel.operations):
        indexes = IndexOfNodesThatUseOutput(cModel, c.output)

        if not indexes:
            continue
        else:
            lastCycle = max(indexes)

        # In order to prevent operations that write on top of their input
        lastCycle += 1

        # Very simple memory calculation, might be wrong, especially if we decide to add padding and stuff like that. Need to make this more customizable.
        # TODO: We are also not handling the fact that some layers might support different tensor types.
        memoryRequired = 4  # Size of a float
        for dim in c.outputDimensions:
            memoryRequired *= dim

        memoryAllocations.append(MemoryAllocation(index, lastCycle, memoryRequired))

    totalTempMemoryNeeded, offsets = CalculateOptimalMemoryAllocationOffset(
        memoryAllocations
    )
    cModel.tempMemoryNeeded = totalTempMemoryNeeded

    ptr = 0
    for index, c in enumerate(cModel.operations):
        indexes = IndexOfNodesThatUseOutput(cModel, c.output)

        if not indexes:
            continue

        c.outputMemoryAddress = MemoryLocation(offsets[ptr], MemoryType.TEMP)
        ptr += 1

    totalOutputMemory = 0
    outputOffsets = []
    for index, c in enumerate(cModel.operations):
        indexes = IndexOfNodesThatUseOutput(cModel, c.output)

        if indexes:
            continue

        # TODO: Support different tensor types and whatnot.
        memoryRequired = 4  # Size of a float
        for dim in c.outputDimensions:
            memoryRequired *= dim

        outputOffsets.append(totalOutputMemory)
        c.outputMemoryAddress = MemoryLocation(totalOutputMemory, MemoryType.OUTPUT)
        totalOutputMemory += memoryRequired

    cModel.outputMemoryNeeded = totalOutputMemory
