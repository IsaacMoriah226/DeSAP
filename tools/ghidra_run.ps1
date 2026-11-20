# Runs a script of DeSAP\ghidra_scripts on the analyzed eboot without changing the project.
#   .\ghidra_run.ps1 FindStringUsers.java C:\Dev\DeSArchi\work\out.txt 80 SetEventFlag
param([Parameter(Mandatory)][string]$Script, [Parameter(ValueFromRemainingArguments)][string[]]$ScriptArgs)
$env:TEMP = 'C:\Dev\DeSArchi\work\tmp'; $env:TMP = 'C:\Dev\DeSArchi\work\tmp'
$env:JAVA_HOME = 'C:\Dev\DeSArchi\tools\jdk-25.0.5.1+2'
$env:MAXMEM = '16G'
& 'C:\Dev\DeSArchi\tools\ghidra_12.2_PUBLIC\support\analyzeHeadless.bat' 'C:\Dev\DeSArchi\ghidra_projects' 'DeS_01.007.000' `
	-process 'eboot_01.007.000.elf' -noanalysis -readOnly -scriptPath "$PSScriptRoot\..\ghidra_scripts" `
	-postScript $Script @ScriptArgs *> 'C:\Dev\DeSArchi\work\ghidra-script.log'
"exit $LASTEXITCODE"
