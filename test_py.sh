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

python -m pylint bo.py
check_ret $? "pylint bo.py"

python -m pycodestyle --max-line-length=120 bo.py
check_ret $? "pycodestyle bo.py"

python -m pylint bo.py
check_ret $? "pylint bo-server.py"

python -m pycodestyle --max-line-length=120 bo.py
check_ret $? "pycodestyle bo-server.py"