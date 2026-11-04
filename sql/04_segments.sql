-- Исследовательская сегментация по категориям объявлений, не подтверждающие тесты.
SELECT category, variant, SUM(exposed) AS users, SUM(contacted) AS contacts,
       ROUND(100.0*SUM(contacted)/NULLIF(SUM(exposed),0),2) AS contact_conversion_pct
FROM user_funnel_mart
GROUP BY category, variant ORDER BY category, variant;
