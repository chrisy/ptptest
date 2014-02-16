#!/bin/sh
rm -rf build
rm -f ptptest-win32.zip
/c/Python27-win32/python.exe build-binary.py build
cd build
mv exe.win32-2.7 ptptest-win32
/c/cygwin/bin/zip -r ../ptptest-win32.zip ptptest-win32
