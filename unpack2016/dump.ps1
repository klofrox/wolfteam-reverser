param([string]$Dll, [string]$Out, [string]$GameDir, [int]$WaitMs = 3000)
# Loads a packed DLL into this (32-bit) process so its packer stub unpacks it, then writes the
# mapped image (SizeOfImage bytes from the module base) to $Out. Unreadable pages are zero-filled.
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class D {
  [DllImport("kernel32", SetLastError=true, CharSet=CharSet.Unicode)] public static extern bool SetDllDirectory(string p);
  [DllImport("kernel32", SetLastError=true, CharSet=CharSet.Unicode)] public static extern IntPtr LoadLibraryW(string p);
  [DllImport("kernel32", SetLastError=true)] public static extern bool ReadProcessMemory(IntPtr h, IntPtr a, byte[] b, int n, out int r);
  [DllImport("kernel32")] public static extern IntPtr GetCurrentProcess();
}
"@
[Environment]::CurrentDirectory = $GameDir
Set-Location $GameDir
[D]::SetDllDirectory($GameDir) | Out-Null
$h = [D]::LoadLibraryW($Dll)
if ($h -eq [IntPtr]::Zero) { Write-Output ("LoadLibrary failed: " + [Runtime.InteropServices.Marshal]::GetLastWin32Error()); exit 1 }
Write-Output ("base 0x{0:x}" -f $h.ToInt64())
Start-Sleep -Milliseconds $WaitMs
$pe = [Runtime.InteropServices.Marshal]::ReadInt32($h, 0x3c)
$size = [Runtime.InteropServices.Marshal]::ReadInt32($h, $pe + 24 + 56)
Write-Output ("SizeOfImage 0x{0:x}" -f $size)
$buf = New-Object byte[] $size
$page = New-Object byte[] 4096
$proc = [D]::GetCurrentProcess()
$bad = 0
for ($o = 0; $o -lt $size; $o += 4096) {
  $r = 0
  if ([D]::ReadProcessMemory($proc, [IntPtr]($h.ToInt64() + $o), $page, 4096, [ref]$r)) { [Array]::Copy($page, 0, $buf, $o, 4096) } else { $bad++ }
}
[IO.File]::WriteAllBytes($Out, $buf)
Write-Output "unreadable pages: $bad"
