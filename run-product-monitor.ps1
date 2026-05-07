param(
  [string]$Product,
  [int]$TargetPrice = 0,
  [int]$MinPrice = 0,
  [int]$MaxPrice = 0,
  [switch]$Loop,
  [int]$IntervalSeconds = 120,
  [string]$EnvFile,
  [switch]$NoAlertFirstSeen
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Script = Join-Path $Root "product_price_monitor.py"
$Config = Join-Path $Root "product_monitor_config.json"

$Args = @($Script, "--config", $Config)
if ($EnvFile) {
  $Args += @("--env-file", $EnvFile)
}
if ($Product) {
  $Args += @("--watch", $Product)
}
if ($TargetPrice -gt 0) {
  $Args += @("--target-price", $TargetPrice)
}
if ($MinPrice -gt 0) {
  $Args += @("--min-price", $MinPrice)
}
if ($MaxPrice -gt 0) {
  $Args += @("--max-price", $MaxPrice)
}
if ($NoAlertFirstSeen) {
  $Args += "--no-alert-first-seen"
}
if ($Loop) {
  $Args += @("--loop", "--interval", $IntervalSeconds)
} else {
  $Args += "--once"
}

python @Args
