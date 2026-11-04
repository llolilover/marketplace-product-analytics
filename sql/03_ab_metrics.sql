-- Primary: уникальные пользователи с контактом / уникальные экспонированные пользователи.
-- Secondary: сообщения; guardrails: ошибки интерфейса и жалобы.
SELECT variant, SUM(exposed) AS exposed, SUM(viewed) AS viewed,
       SUM(contacted) AS contacted, SUM(messaged) AS messaged,
       SUM(ui_error) AS ui_error, SUM(complaint) AS complaints,
       ROUND(100.0*SUM(contacted)/NULLIF(SUM(exposed),0), 3) AS contact_conversion_pct,
       ROUND(100.0*SUM(messaged)/NULLIF(SUM(exposed),0), 3) AS message_conversion_pct
FROM user_funnel_mart GROUP BY variant ORDER BY variant;
