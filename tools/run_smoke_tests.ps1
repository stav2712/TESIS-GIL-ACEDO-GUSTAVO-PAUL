param(
  [Parameter(Mandatory=$true)][string]$AdminPassword,
  [string]$AdminUser = "admin",
  [switch]$DeepNl
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$argsList = @(
  "tools/smoke_test_tesis.py",
  "--admin-user", $AdminUser,
  "--admin-pass", $AdminPassword
)

if ($DeepNl) {
  $argsList += "--deep-nl"
}

python @argsList
exit $LASTEXITCODE
