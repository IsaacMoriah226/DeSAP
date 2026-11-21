# Runs a script of DeSAP\ghidra_scripts on the analyzed eboot without changing the project.
#   .\ghidra_run.ps1 FindStringUsers.java <work>\out.txt 80 SetEventFlag
# Paths are the workspace's (the folder holding DeSAP; docs/SETUP.md): work, tools (Ghidra, JDK), ghidra_projects.
param([Parameter(Mandatory)][string]$Script, [Parameter(ValueFromRemainingArguments)][string[]]$ScriptArgs)
$Workspace = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$env:TEMP = "$Workspace\work\tmp"; $env:TMP = "$Workspace\work\tmp"
$env:JAVA_HOME = "$Workspace\tools\jdk-25.0.5.1+2"
$env:MAXMEM = '16G'
& "$Workspace\tools\ghidra_12.2_PUBLIC\support\analyzeHeadless.bat" "$Workspace\ghidra_projects" 'DeS_01.007.000' `
	-process 'eboot_01.007.000.elf' -noanalysis -readOnly -scriptPath "$PSScriptRoot\..\ghidra_scripts" `
	-postScript $Script @ScriptArgs *> "$Workspace\work\ghidra-script.log"
"exit $LASTEXITCODE"
