-- In-boundary development work. Scenario C.
--
-- northstar.marketing_leads is inside the active domain and in DEV, so Zence
-- allows this silently — no prompt, no interruption. A guardrail that announces
-- itself on safe work is a guardrail people turn off.

SELECT
    lead_id,
    source_campaign,
    created_at
FROM northstar.marketing_leads
WHERE created_at >= DATEADD(day, -30, CURRENT_DATE())
