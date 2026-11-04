-- Одна строка = один пользователь, единица рандомизации A/B-теста.
-- Учитываем причинно-временной порядок шагов воронки.
DROP TABLE IF EXISTS user_funnel_mart;
CREATE TABLE user_funnel_mart AS
WITH event_times AS (
  SELECT a.user_id, a.variant, a.assigned_at, a.listing_id,
         u.device, u.region, l.category,
         MIN(CASE WHEN e.event_type='exposure' THEN e.event_at END) AS exposure_at,
         MIN(CASE WHEN e.event_type='listing_view' THEN e.event_at END) AS view_at,
         MIN(CASE WHEN e.event_type='contact_click' THEN e.event_at END) AS contact_at,
         MIN(CASE WHEN e.event_type='message_sent' THEN e.event_at END) AS message_at,
         MIN(CASE WHEN e.event_type='ui_error' THEN e.event_at END) AS error_at,
         MIN(CASE WHEN e.event_type='complaint' THEN e.event_at END) AS complaint_at
  FROM assignments a
  JOIN users u ON u.user_id=a.user_id
  JOIN listings l ON l.listing_id=a.listing_id
  LEFT JOIN clean_events e ON e.user_id=a.user_id AND e.listing_id=a.listing_id
  GROUP BY a.user_id, a.variant, a.assigned_at, a.listing_id, u.device, u.region, l.category
)
SELECT user_id, variant, assigned_at, device, region, category,
       CASE WHEN exposure_at IS NOT NULL THEN 1 ELSE 0 END AS exposed,
       CASE WHEN view_at>=exposure_at THEN 1 ELSE 0 END AS viewed,
       CASE WHEN contact_at>=view_at AND view_at>=exposure_at THEN 1 ELSE 0 END AS contacted,
       CASE WHEN message_at>=contact_at AND contact_at>=view_at AND view_at>=exposure_at THEN 1 ELSE 0 END AS messaged,
       CASE WHEN error_at>=exposure_at THEN 1 ELSE 0 END AS ui_error,
       CASE WHEN complaint_at>=view_at AND view_at>=exposure_at THEN 1 ELSE 0 END AS complaint
FROM event_times;
CREATE UNIQUE INDEX ix_funnel_user ON user_funnel_mart(user_id);
