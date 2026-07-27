-- Daily revenue fact. Feeds the executive revenue dashboard.
--
-- Editing this file is Scenario B: Zence reads DataHub lineage, sees that
-- northstar_revenue depends on it, and asks for approval before the change
-- lands rather than after someone notices the dashboard moved.

{{ config(materialized='table') }}

SELECT
    o.close_date                          AS revenue_date,
    SUM(o.amount)                         AS gross_revenue,
    SUM(o.amount) - SUM(o.discount)       AS net_revenue,
    COUNT(*)                              AS order_count
FROM {{ ref('crm_opportunities') }} o
JOIN {{ ref('dim_customer') }} c
  ON c.customer_id = o.customer_id
WHERE o.stage = 'closed_won'
GROUP BY 1
