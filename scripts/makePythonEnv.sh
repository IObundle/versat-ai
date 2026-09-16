#!/bin/bash

minorV="$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[1:2])))')"
force=0

if [[ -z $minorV ]]; then
   echo "Error, we require python3 to be installed and accessible"
else
   mkdir ../python_env
   pushd ../python_env
   python3 -m "venv" .
   source ./bin/activate

   if [[ $force -eq 1 ]]; then
      # Should work for any pthon version above >3.11
      pip install onnx==1.17.0 skl2onnx==1.17.0 matplotlib==3.10.3 onnxruntime==1.24.4 pydot==4.0.1 protobuf==7.36.1 numpy==2.2.6 scikit_learn==1.7.2 onnxconverter_common==1.16.0 pillow==12.3.0 contourpy==1.3.2 python_dateutil==2.9.0 pyparsing==3.3.2 packaging==26.3 kiwisolver==1.5.1 cycler==0.12.1 fonttools==4.65.0 sympy==1.14.0 flatbuffers==25.12.19 coloredlogs==15.0.1 six==1.17.0 joblib==1.6.0 scipy==1.15.3 threadpoolctl==3.7.0 humanfriendly==10.0 mpmath==1.3.0 cloudpickle==3.1.2
   else
      if [[ $minorV -ge 11 ]]; then
         pip install onnx==1.17.0 skl2onnx==1.17.0 matplotlib==3.10.3 onnxruntime==1.24.4 pydot==4.0.1 protobuf==7.36.1
      else
         pip install onnx==1.17.0 skl2onnx==1.17.0 matplotlib==3.10.3 onnxruntime==1.22.0 pydot==4.0.1 protobuf==7.36.1
      fi
   fi
fi
