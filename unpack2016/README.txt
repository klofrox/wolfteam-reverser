WolfTeam 2016 cshell.dll / object.lto unpack (packed with random section names, code encrypted).

1) Dump (32-bit PowerShell; the game install must exist, its DLLs are loaded from there):
   C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -File dump.ps1 ^
     -Dll <path>\cshell.dll -Out cshell_2016.mem -GameDir "C:\Program Files (x86)\Softnyx\WolfTeam-US"
   It prints the load base (e.g. base 0x6c240000).
2) Make a loadable PE (raw layout = virtual layout, ImageBase = that base):
   python fixpe.py cshell_2016.mem cshell_2016.dll 6c240000
3) Open in Ghidra / IDA (x86 32-bit PE). Imports are not rebuilt (calls go through the packer's thunks).

Helpers (python + capstone): pesec.py sections/entropy, dis.py <mem> <base> <addr[:n]> disassemble,
dispscan.py find [reg+disp] uses, callers.py find CALL rel32 callers, fmatch.py match 2013 functions in a 2016 dump.
Known addresses: webport/docs/NOTES.md ("2016 RE"), docs/movement.md ("2016 check").
