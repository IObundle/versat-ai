#!/usr/bin/python3

import sys
import json
import argparse
import subprocess as sp
import copy
from pprint import pprint
from enum import Enum, auto
from dataclasses import dataclass

sys.path.append("./scripts")

from generateSimpleTests import GenerateSimpleTest
from onnxMain import GenerateDebug

# TODO: FIXED_LIST instead of encoding the models, it could encode the name of the tests themselves.
#       That way we would not need to repeat the path and focusLayer everytime, we just create a Fixed test and then
#       add the name of the test to the Fixed_list


class TestType(Enum):
    GENERATED = auto()
    FIXED = auto()
    FIXED_LIST = auto()


class TestMode(Enum):
    DEFAULT = auto()
    SOFTWARE = auto()
    VERSAT = auto()


def OverrideTestMode(stronger, weaker):
    if stronger == TestMode.DEFAULT:
        return weaker

    return stronger


@dataclass
class TestConfiguraton:
    focusLayer: int | None = None
    mode: TestMode = TestMode.DEFAULT


@dataclass
class SubTest:
    name: str
    config: TestConfiguraton


@dataclass
class Test:
    type: TestType
    path: str
    subTest: list[SubTest] = None


def ParseTestName(testName):
    splitted = testName.split("_")

    originalName = splitted[0]

    config = TestConfiguraton()
    for x in splitted[1:]:
        if x == "PC":
            config.mode = TestMode.SOFTWARE
        elif x == "VERSAT":
            config.mode = TestMode.VERSAT

        try:
            asInt = int(x)
            config.focusLayer = asInt
        except:
            pass

    return originalName, config


def ParseTest(testName, testInfo, allTests):
    testType = TestType[testInfo["type"]]
    path = testInfo.get("path", None)
    subTests = testInfo.get("subTests", None)

    parsedSubTests = [SubTest(testName, TestConfiguraton())]
    if subTests:
        parsedSubTests = []
        for name in subTests:
            subTestName, subTestConfigs = ParseTestName(name)
            sub = SubTest(subTestName, subTestConfigs)
            parsedSubTests.append(sub)

    test = Test(testType, path, parsedSubTests)

    return test


def ParseTests(testInfoJson):
    tests = {}
    for name in testInfoJson:
        test = ParseTest(name, testInfoJson[name], tests)
        tests[name] = test

    return tests


def SubTestName(subTest):
    name = str(subTest.name)

    if subTest.config.mode == TestMode.SOFTWARE:
        name = name + "_PC"

    if subTest.config.focusLayer:
        name = name + "_" + str(subTest.config.focusLayer)

    return name


if __name__ == "__main__":
    testInfoJson = None
    jsonTestInfoPath = "tests.json"

    try:
        with open(jsonTestInfoPath, "r") as file:
            testInfoJson = json.load(file)
    except Exception as e:
        print(f"Error parsing json file that should contain tests info: {e}")
        sys.exit(-1)
    testNames = [x for x in testInfoJson.keys()]

    print(testNames)

    if len(sys.argv) != 2:
        print(
            "Need one and only one argument, the test name (append a final _<focusLayer> to only perform one layer of the test)"
        )
        sys.exit(-1)

    allTests = ParseTests(testInfoJson)
    properName, configs = ParseTestName(sys.argv[1])

    test = allTests[properName]

    for subTest in test.subTest:
        subTest.config.mode = OverrideTestMode(subTest.config.mode, configs.mode)
        if configs.focusLayer:
            subTest.config.focusLayer = configs.focusLayer

    # NOTE: We run from the makefile since we need to enter the python environment but we do not want to run this script from inside the environment.
    # TODO: Can we run from inside the environment and call nix? We cannot do the inverse I think but I do not know if we tried nix from inside python env.

    createVCD = False
    if test.type == TestType.GENERATED:
        createVCD = True

    boolStr = "true" if createVCD else "false"
    with open("./software/src/testInfo.h", "w") as f:
        f.write("\n".join([f'#include "{x.name}_modelInfo.h"' for x in test.subTest]))
        f.write("\n\n")

        f.write(f'#define TEST_NAME "{properName}"\n')
        f.write(f"#define CREATE_VCD {boolStr}\n\n")

        f.write(f"static TestModelInfo* testModels[] = " + "{\n")
        f.write(",\n".join([f"  &{x.name}_ModelInfo" for x in test.subTest]))
        f.write("\n};\n")

    if test.type == TestType.GENERATED:
        GenerateSimpleTest("./tests/generated/")
        GenerateDebug(
            "tests/generated/",
            "model.onnx",
            "software/",
            "software/src",
            properName,
            test.subTest[0].config.focusLayer,
            test.subTest[0].config.mode == TestMode.SOFTWARE,
        )
    elif test.type == TestType.FIXED or test.type == TestType.FIXED_LIST:
        for subTest in test.subTest:
            properTest = allTests[subTest.name]
            GenerateDebug(
                properTest.path,
                "model.onnx",
                "software/",
                "software/src",
                subTest.name,
                subTest.config.focusLayer,
                subTest.config.mode == TestMode.SOFTWARE,
            )
