[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outputDirectory = Join-Path $projectRoot "diagnostics\bsod-$timestamp"
$reportPath = Join-Path $outputDirectory "report.txt"

New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null

function Add-Section {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Title,

        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    Add-Content -LiteralPath $reportPath -Value ""
    Add-Content -LiteralPath $reportPath -Value ("===== {0} =====" -f $Title)
    try {
        $result = & $Command | Out-String -Width 4096
        Add-Content -LiteralPath $reportPath -Value $result
    }
    catch {
        Add-Content -LiteralPath $reportPath -Value ("Collection error: {0}" -f $_.Exception.Message)
    }
}

Set-Content -LiteralPath $reportPath -Value "1553B BSOD diagnostic report"
Add-Content -LiteralPath $reportPath -Value ("Collected: {0}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"))
Add-Content -LiteralPath $reportPath -Value ("Computer: {0}" -f $env:COMPUTERNAME)

Add-Section "Operating system" {
    Get-CimInstance Win32_OperatingSystem |
        Select-Object Caption, Version, BuildNumber, OSArchitecture, LastBootUpTime
}

Add-Section "Computer and BIOS" {
    Get-CimInstance Win32_ComputerSystem |
        Select-Object Manufacturer, Model, SystemType, TotalPhysicalMemory
    Get-CimInstance Win32_BIOS |
        Select-Object Manufacturer, SMBIOSBIOSVersion, ReleaseDate
}

Add-Section "Relevant kernel services" {
    Get-CimInstance Win32_SystemDriver |
        Where-Object {
            $_.Name -match "AdvCan|PMC1553" -or
            $_.DisplayName -match "AdvCan|PMC1553|1553" -or
            $_.PathName -match "AdvCan|PMC1553"
        } |
        Select-Object Name, DisplayName, State, StartMode, PathName
}

Add-Section "Relevant driver files" {
    $driverDirectory = Join-Path $env:SystemRoot "System32\drivers"
    Get-ChildItem -LiteralPath $driverDirectory -File |
        Where-Object { $_.Name -match "AdvCan|PMC1553" } |
        ForEach-Object {
            [PSCustomObject]@{
                FullName = $_.FullName
                Length = $_.Length
                LastWriteTime = $_.LastWriteTime
                FileVersion = $_.VersionInfo.FileVersion
                ProductVersion = $_.VersionInfo.ProductVersion
                Company = $_.VersionInfo.CompanyName
                Signature = (Get-AuthenticodeSignature -LiteralPath $_.FullName).Status
            }
        }
}

Add-Section "Relevant signed PnP drivers" {
    Get-CimInstance Win32_PnPSignedDriver |
        Where-Object {
            $_.DeviceName -match "Advantech|CAN|1553|PMC" -or
            $_.DriverName -match "AdvCan|PMC1553"
        } |
        Select-Object DeviceName, DeviceID, DriverName, DriverVersion,
            DriverDate, Manufacturer, InfName, IsSigned
}

Add-Section "Relevant PnP devices" {
    Get-PnpDevice |
        Where-Object {
            $_.FriendlyName -match "Advantech|CAN|1553|PMC" -or
            $_.InstanceId -match "VEN_10B5|AdvCan|PMC1553"
        } |
        Select-Object Status, Class, FriendlyName, InstanceId, Problem
}

Add-Section "Recent bugcheck events" {
    Get-WinEvent -FilterHashtable @{ LogName = "System"; Id = 1001 } -MaxEvents 10 |
        Select-Object TimeCreated, ProviderName, Id, LevelDisplayName, Message
}

Add-Section "Recent unexpected shutdown events" {
    Get-WinEvent -FilterHashtable @{ LogName = "System"; Id = 41 } -MaxEvents 10 |
        Select-Object TimeCreated, ProviderName, Id, LevelDisplayName, Message
}

Add-Section "Installed third-party driver packages" {
    & pnputil.exe /enum-drivers
}

$minidumpDirectory = Join-Path $env:SystemRoot "Minidump"
$latestDump = Get-ChildItem -Path (Join-Path $minidumpDirectory "*.dmp") -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if ($null -ne $latestDump) {
    Copy-Item -LiteralPath $latestDump.FullName -Destination $outputDirectory -Force
    Add-Content -LiteralPath $reportPath -Value ""
    Add-Content -LiteralPath $reportPath -Value ("Copied minidump: {0}" -f $latestDump.Name)
}
else {
    Add-Content -LiteralPath $reportPath -Value ""
    Add-Content -LiteralPath $reportPath -Value "No minidump was found."
}

$memoryDump = Join-Path $env:SystemRoot "MEMORY.DMP"
if (Test-Path -LiteralPath $memoryDump) {
    $memoryDumpFile = Get-Item -LiteralPath $memoryDump
    Add-Content -LiteralPath $reportPath -Value (
        "Full memory dump exists: {0} ({1} bytes)" -f
        $memoryDumpFile.FullName,
        $memoryDumpFile.Length
    )
}

Write-Host ("Diagnostics saved to: {0}" -f $outputDirectory)
Write-Host "Copy this directory back to the development computer."
