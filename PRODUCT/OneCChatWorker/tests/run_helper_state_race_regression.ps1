param([string]$ScratchRoot)
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSScriptRoot 'TestScratch.psm1') -Force -DisableNameChecking
$node=Get-Command node.exe -ErrorAction Stop
$owned=$null
try{
 if([string]::IsNullOrWhiteSpace($ScratchRoot)){
  $owned=New-OneCTestScratch -Purpose 'HelperStateRace'
  $ScratchRoot=$owned.path
 }else{
  New-Item -ItemType Directory -Force -Path $ScratchRoot|Out-Null
 }
 $out=Join-Path $ScratchRoot 'helper-state-race.out.txt'
 $err=Join-Path $ScratchRoot 'helper-state-race.err.txt'
 $run=Join-Path $ScratchRoot 'run'
 $p=Start-Process -FilePath $node.Source -ArgumentList @((Join-Path $PSScriptRoot 'helper-state-race-regression.mjs'),$run) -RedirectStandardOutput $out -RedirectStandardError $err -NoNewWindow -Wait -PassThru
 $stdout=$(if(Test-Path $out){Get-Content $out -Raw -Encoding UTF8}else{''})
 $stderr=$(if(Test-Path $err){Get-Content $err -Raw -Encoding UTF8}else{''})
 if($p.ExitCode -ne 0){throw ("HELPER_STATE_RACE_REGRESSION_FAILED exit={0} stderr={1} stdout={2}" -f $p.ExitCode,$stderr,$stdout)}
 if($stdout -notmatch 'HELPER_STATE_RACE_REGRESSION_PASS checks=8'){throw 'HELPER_STATE_RACE_PASS_MARKER_MISSING'}
 Write-Host $stdout.Trim()
 Write-Host 'HELPER_STATE_RACE_PS51_WRAPPER_PASS'
}finally{
 if($owned){Remove-OneCTestScratch -Path $owned.path -RunId $owned.run_id -Base $owned.base|Out-Null}
}
