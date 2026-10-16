#!/bin/sh
# usage: tools/ghidra/run.sh <program> <Script.java> <args...>   (project re/ghidra_proj, no re-analysis)
cd "$(dirname "$0")/../.."
export JAVA_HOME="C:/Users/unaut/tools/jdk-21.0.12.1+1"
prog="$1"; script="$2"; shift 2
"/c/Users/unaut/tools/ghidra_12.1.4_PUBLIC/support/analyzeHeadless.bat" "$(cygpath -w re/ghidra_proj)" wolfteam \
  -process "$prog" -noanalysis -readOnly -scriptPath "$(cygpath -w tools/ghidra)" -postScript "$script" "$@" > re/out/last_run.log 2>&1
grep -E "ERROR|Exception" re/out/last_run.log | head -5
