-- Устраняем дубли по event_id и события до вступления пользователя в эксперимент.
-- Оконная функция позволяет выбрать ровно одну запись на идентификатор события.
DROP TABLE IF EXISTS clean_events;
CREATE TABLE clean_events AS
WITH numbered AS (
  SELECT e.*,
         ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY event_at, rowid) AS rn
  FROM raw_events e
)
SELECT e.event_id, e.user_id, e.listing_id, e.event_type, e.event_at
FROM numbered e
JOIN assignments a ON a.user_id = e.user_id AND a.listing_id = e.listing_id
JOIN listings l ON l.listing_id = e.listing_id
WHERE e.rn = 1 AND e.event_at >= a.assigned_at;
CREATE INDEX ix_clean_user_type ON clean_events(user_id, event_type);
