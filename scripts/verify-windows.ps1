# Run in the Windows guest as Administrator. Reads devices; changes no settings.
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$secureBoot = try { Confirm-SecureBootUEFI } catch { $_.Exception.Message }
[ordered]@{
    SecureBoot = $secureBoot
    MemoryGiB = [Math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 2)
    Video = @(Get-CimInstance Win32_VideoController |
        Select-Object Name,Status,ConfigManagerErrorCode,DriverVersion,
                      CurrentHorizontalResolution,CurrentVerticalResolution,CurrentRefreshRate)
    Receiver = @(Get-PnpDevice -PresentOnly |
        Where-Object { $_.InstanceId -like '*VID_046D&PID_C534*' } |
        Select-Object Class,FriendlyName,Status)
} | ConvertTo-Json -Depth 5
