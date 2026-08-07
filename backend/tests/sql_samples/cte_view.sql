CREATE VIEW db.v_cte AS
WITH cte AS (
    SELECT x, y
    FROM db.t1
)
SELECT cte.x, t2.y
FROM cte
JOIN db.t2 t2 ON cte.x = t2.x
