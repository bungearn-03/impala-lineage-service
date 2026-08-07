CREATE VIEW db.v_join AS
SELECT o.order_id, c.customer_name
FROM db.orders o
LEFT JOIN db.customers c ON o.customer_id = c.customer_id
