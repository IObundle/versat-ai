#!/usr/bin/python3

import sys
import json
import argparse
import subprocess as sp
from enum import Enum, auto
from dataclasses import dataclass


class TestType(Enum):
    GENERATED = (auto(),)
    FIXED = auto()


@dataclass
class Test:
    type: TestType
    path: str = None


def ValidateTest(test: Test):
    if test.type == TestType.FIXED:
        assert test.path != None


def ParseTest(testJsonContent):
    try:
        testType = TestType[testJsonContent["type"]]
        path = testJsonContent.get("path", None)

        test = Test(testType, path)
        ValidateTest(test)

        return test
    except Exception as e:
        print(f"Error parsing the json: {e}")
        sys.exit(-1)


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

    parser = argparse.ArgumentParser(
        prog="Tester", description="Setup for a single test"
    )
    parser.add_argument("TestName", choices=testNames)

    arguments = parser.parse_args()

    testName = arguments.TestName
    test = ParseTest(testInfoJson[testName])

    # NOTE: We run from the makefile since we need to enter the python environment but we do not want to run this script from inside the environment.
    # TODO: Can we run from inside the environment and call nix? We cannot do the inverse I think but I do not know if we tried nix from inside python env.

    createVCD = False
    if test.type == TestType.GENERATED:
        createVCD = True

    boolStr = "true" if createVCD else "false"
    with open("./software/src/testInfo.h", "w") as f:
        f.write(f'#define TEST_NAME "{testName}"\n')
        f.write(f"#define CREATE_VCD {boolStr}\n")

    if test.type == TestType.GENERATED:
        try:
            sp.run(["make", "test-generate"])
        except Exception as e:
            print(f"Failed to generate test: {e}")
            sys.exit(-1)
    else:
        try:
            sp.run(["make", "do-test", f"TEST_PATH={test.path}"])
        except Exception as e:
            print(f"Failed to generate test: {e}")
            sys.exit(-1)

    try:
        sp.run(["make", "test-setup"])
    except Exception as e:
        print(f"Failed to generate test: {e}")
        sys.exit(-1)
