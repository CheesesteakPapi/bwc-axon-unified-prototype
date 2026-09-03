[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourceCsv,

    [Parameter(Mandatory = $true)]
    [string]$UserOutputCsv,

    [Parameter(Mandatory = $true)]
    [string]$GroupEntityOutputCsv
)

$ErrorActionPreference = 'Stop'

$sourceRows = Import-Csv -LiteralPath $SourceCsv
if (-not $sourceRows) {
    throw "The source CSV contains no data rows."
}

$requiredSourceHeaders = @(
    'ExternalId', 'Email', 'BadgeNumber', 'FirstName', 'LastName', 'Status',
    'Username', 'Role', 'SupervisorEmail', 'Location', 'Phone', 'Rank',
    'GroupExternalId'
)
$actualSourceHeaders = @($sourceRows[0].PSObject.Properties.Name)
$missingSourceHeaders = @($requiredSourceHeaders | Where-Object { $_ -notin $actualSourceHeaders })
if ($missingSourceHeaders.Count -gt 0) {
    throw "The source CSV is missing required headers: $($missingSourceHeaders -join ', ')"
}

foreach ($outputPath in @($UserOutputCsv, $GroupEntityOutputCsv)) {
    $parent = Split-Path -Parent $outputPath
    if (-not [string]::IsNullOrWhiteSpace($parent) -and -not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
}

$userRows = @(foreach ($row in $sourceRows) {
    [pscustomobject][ordered]@{
        EXTERNAL_ID          = $row.ExternalId
        EMAIL                = $row.Email
        BADGE_NUMBER         = $row.BadgeNumber
        FIRST_NAME           = $row.FirstName
        LAST_NAME            = $row.LastName
        STATUS               = $row.Status
        USERNAME             = $row.Username
        ROLE                 = $row.Role
        SUPERVISOR_EMAIL     = $row.SupervisorEmail
        LOCATION             = $row.Location
        EVIDENCE_GROUP_EXT_ID = ''
        PHONE                = $row.Phone
        RANK                 = $row.Rank
    }
})

$groupRows = @(foreach ($row in $sourceRows) {
    $membershipType = if ([string]::IsNullOrWhiteSpace($row.MembershipType)) {
        'MEMBER'
    } else {
        $row.MembershipType.Trim().ToUpperInvariant()
    }
    foreach ($groupExternalId in @($row.GroupExternalId -split ';')) {
        $groupExternalId = $groupExternalId.Trim()
        if ([string]::IsNullOrWhiteSpace($groupExternalId)) {
            continue
        }
        [pscustomobject][ordered]@{
            EXTERNAL_ID     = $groupExternalId
            MEMBERSHIP_TYPE = $membershipType
            ENTITY_TYPE     = 'USER'
            ENTITY_ID       = $row.Email
        }
    }
})

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$userLines = @($userRows | ConvertTo-Csv -NoTypeInformation)
[System.IO.File]::WriteAllLines([System.IO.Path]::GetFullPath($UserOutputCsv), $userLines, $utf8NoBom)
if ($groupRows.Count -gt 0) {
    $groupLines = @($groupRows | ConvertTo-Csv -NoTypeInformation)
    [System.IO.File]::WriteAllLines([System.IO.Path]::GetFullPath($GroupEntityOutputCsv), $groupLines, $utf8NoBom)
} else {
    [System.IO.File]::WriteAllText(
        [System.IO.Path]::GetFullPath($GroupEntityOutputCsv),
        "EXTERNAL_ID,MEMBERSHIP_TYPE,ENTITY_TYPE,ENTITY_ID`r`n",
        $utf8NoBom
    )
}

Write-Host "Created $($userRows.Count) user rows: $UserOutputCsv"
Write-Host "Created $($groupRows.Count) group-member rows: $GroupEntityOutputCsv"
