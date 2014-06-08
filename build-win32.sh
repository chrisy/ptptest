#!/bin/sh
set -e

cygwin=
if uname -a | grep -q Cygwin; then
	cygwin=1
	python=python
else
	python="/c/Python27-win32/python.exe"
fi

if [ "$cygwin" ]; then
	# Workaround cx_Freeze oddness on Cygwin - the files are stored
	# with .exe on the end but it doesn't look for .exe on Cygwin!
	dir=$(python -c "
	import os, cx_Freeze
	print os.path.join(os.path.dirname(cx_Freeze.__file__), 'bases')
	")
	#for base in Console ConsoleKeepPath; do
	#	(cd $dir && cp $base.exe $base)
	#done
fi

rm -rf build
rm -f ptptest-win32.zip
$python build-binary.py build
cd build
mv exe.* ptptest-win32
cp ../win32/*.exe ptptest-win32
if [ "$cygwin" ]; then
	for i in ptpclient ptpserver; do
		mv ptptest-win32/$i ptptest-win32/$i.exe
	done
fi
zip -9 -r ../ptptest-win32.zip ptptest-win32
