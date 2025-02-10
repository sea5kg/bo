#!/bin/bash

check_ret() {
    if [ $1 -ne 0 ]; then
        echo ""
        echo "!!! FAIL: $2"
        echo "********************************************************************************"
        echo ""
        exit $1
    else
        echo ""
        echo "*** SUCCESS: $2"
        echo "********************************************************************************"
        echo ""
    fi
}

python3 -m pylint bo.py
check_ret $? "pylint bo.py"

python3 -m pycodestyle --max-line-length=100 bo.py
check_ret $? "pycodestyle bo.py"

python3 -m pylint bo_server.py
check_ret $? "pylint bo_server.py"

python3 -m pycodestyle --max-line-length=100 bo_server.py
check_ret $? "pycodestyle bo_server.py"