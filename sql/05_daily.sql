SELECT SUBSTR(assigned_at,1,10) AS day, variant,
       SUM(exposed) AS exposed, SUM(contacted) AS contacts,
       ROUND(100.0*SUM(contacted)/NULLIF(SUM(exposed),0),2) AS conversion_pct
FROM user_funnel_mart
GROUP BY SUBSTR(assigned_at,1,10), variant ORDER BY day, variant;
