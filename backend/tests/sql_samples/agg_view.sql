CREATE VIEW db.v_agg AS
SELECT customer_id, SUM(amount) AS total_amount
FROM db.orders
GROUP BY customer_id
