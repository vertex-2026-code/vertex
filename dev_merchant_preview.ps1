$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$staticDir = Join-Path $root "static"

function To-JsonText($body) {
    return ($body | ConvertTo-Json -Depth 20)
}

function Response-Text([int]$status, [string]$type, [string]$body) {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
    $statusText = if ($status -eq 200) { "OK" } elseif ($status -eq 404) { "Not Found" } else { "Error" }
    $header = "HTTP/1.1 $status $statusText`r`nContent-Type: $type`r`nContent-Length: $($bytes.Length)`r`nConnection: close`r`n`r`n"
    return @([System.Text.Encoding]::ASCII.GetBytes($header), $bytes)
}

function Response-Json([int]$status, $body) {
    return Response-Text $status "application/json; charset=utf-8" (To-JsonText $body)
}

function Mock-Fallback([string]$skillId) {
    if ($skillId -eq "cold_style_retire") {
        return @{
            skill = $skillId
            cold_candidates = @(
                @{ style_id = "nail_12"; risk_score = 78; suggested_action = "deprioritize"; reason = "low tryons, weak booking, trend down" },
                @{ style_id = "nail_08"; risk_score = 64; suggested_action = "revise"; reason = "low like rate, revise color palette" }
            )
        }
    }
    if ($skillId -eq "automation_queue") {
        return @{
            skill = $skillId
            items = @(
                @{ type = "launch_hot_style"; target = "nail_05"; priority = "high"; status = "ready"; reason = "sweet style converts well" },
                @{ type = "retire_or_revise_cold_style"; target = "nail_12"; priority = "medium"; status = "pending_review"; reason = "watch low conversion style" }
            )
        }
    }
    return @{
        skill = $skillId
        hot_candidates = @(
            @{ style_id = "nail_05"; score = 86; reason = "high tryons, high likes, good shop fit"; actions = @("promote_shop", "generate_variant") },
            @{ style_id = "nail_16"; score = 78; reason = "same-style supporting candidate"; actions = @("promote_shop") }
        )
    }
}

function Parse-Body($raw) {
    $parts = $raw -split "`r`n`r`n", 2
    if ($parts.Length -lt 2 -or [string]::IsNullOrWhiteSpace($parts[1])) {
        return @{}
    }
    try {
        return ($parts[1] | ConvertFrom-Json)
    }
    catch {
        return @{}
    }
}

$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse("127.0.0.1"), 5000)
$listener.Start()

while ($true) {
    $client = $listener.AcceptTcpClient()
    try {
        $stream = $client.GetStream()
        $buffer = New-Object byte[] 65536
        $count = $stream.Read($buffer, 0, $buffer.Length)
        $raw = [System.Text.Encoding]::UTF8.GetString($buffer, 0, $count)
        $firstLine = ($raw -split "`r`n")[0]
        $tokens = $firstLine -split " "
        $method = if ($tokens.Length -gt 0) { $tokens[0] } else { "GET" }
        $path = if ($tokens.Length -gt 1) { ($tokens[1] -split "\?")[0] } else { "/" }

        if ($path -eq "/" -or $path -eq "/merchant") {
            $html = Get-Content -LiteralPath (Join-Path $staticDir "merchant.html") -Raw -Encoding UTF8
            $resp = Response-Text 200 "text/html; charset=utf-8" $html
        }
        elseif ($path -eq "/api/merchant/skills/registry") {
            $resp = Response-Json 200 @{
                skill_ids = @("merchant_style_profile", "periodic_ops_report", "same_style_competitor_analysis", "hot_style_launch", "cold_style_retire", "automation_queue")
                skills = @{
                    merchant_style_profile = @{ name = "Merchant style profile" }
                    periodic_ops_report = @{ name = "Periodic operations report" }
                    same_style_competitor_analysis = @{ name = "Same-style competitor analysis" }
                    hot_style_launch = @{ name = "Hot style launch" }
                    cold_style_retire = @{ name = "Cold style retire" }
                    automation_queue = @{ name = "Automation queue" }
                }
            }
        }
        elseif ($path -eq "/api/merchant/agent/run-skill" -and $method -eq "POST") {
            $body = Parse-Body $raw
            $skillId = if ($body.skill_id) { [string]$body.skill_id } else { "hot_style_launch" }
            $resp = Response-Json 200 @{
                mode = "preview_openclaw_skill"
                skill_id = $skillId
                shop = @{ id = $body.shop_id; name = "Fleur Rose - Wudaokou" }
                period_days = $body.period_days
                openclaw = @{ used = $false; reply = @{ ui_summary = "Preview mode ran skill $skillId" }; error = $null }
                local_fallback = Mock-Fallback $skillId
            }
        }
        elseif ($path -eq "/api/merchant/agent/chat" -and $method -eq "POST") {
            $body = Parse-Body $raw
            $resp = Response-Json 200 @{
                mode = "preview_openclaw_agent_dispatch"
                shop = @{ id = $body.shop_id; name = "Fleur Rose - Wudaokou" }
                period_days = $body.period_days
                openclaw = @{
                    used = $false
                    reply = @{
                        intent = $body.message
                        selected_skills = @("hot_style_launch", "cold_style_retire")
                        ui_summary = "Preview mode selected hot launch and cold retire skills."
                    }
                    error = $null
                }
                local_fallback = @{
                    skills = @{
                        automation_queue = Mock-Fallback "automation_queue"
                    }
                }
            }
        }
        else {
            $resp = Response-Json 404 @{ error = "not found" }
        }

        $stream.Write($resp[0], 0, $resp[0].Length)
        $stream.Write($resp[1], 0, $resp[1].Length)
    }
    catch {
        try {
            $resp = Response-Json 500 @{ error = $_.Exception.Message }
            $stream.Write($resp[0], 0, $resp[0].Length)
            $stream.Write($resp[1], 0, $resp[1].Length)
        }
        catch {}
    }
    finally {
        $client.Close()
    }
}
