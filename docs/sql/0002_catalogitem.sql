--
-- Create model CatalogItem
--
CREATE TABLE `construction_catalogitem` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `name` varchar(200) NOT NULL, `unit` varchar(5) NOT NULL, `unit_price` numeric(12, 2) NOT NULL, `is_custom` bool NOT NULL, `created_at` datetime(6) NOT NULL);
