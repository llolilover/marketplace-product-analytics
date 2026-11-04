SELECT 'duplicate_event_ids' AS issue, COUNT(*)-COUNT(DISTINCT event_id) AS n FROM raw_events
UNION ALL SELECT 'unknown_users', COUNT(*) FROM raw_events e
  LEFT JOIN users u ON u.user_id=e.user_id WHERE u.user_id IS NULL
UNION ALL SELECT 'events_before_assignment', COUNT(*) FROM raw_events e
  JOIN assignments a ON a.user_id=e.user_id WHERE e.event_at<a.assigned_at
UNION ALL SELECT 'orphan_messages', COUNT(*) FROM clean_events e
  WHERE e.event_type='message_sent' AND NOT EXISTS
  (SELECT 1 FROM clean_events c WHERE c.user_id=e.user_id
   AND c.event_type='contact_click' AND c.event_at <= e.event_at);
