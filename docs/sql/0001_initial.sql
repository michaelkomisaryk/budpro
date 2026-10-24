--
-- Create model Project
--
CREATE TABLE `construction_project` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `name` varchar(200) NOT NULL, `address` varchar(255) NOT NULL, `description` longtext NOT NULL, `budget` numeric(14, 2) NOT NULL, `start_date` date NOT NULL, `end_date` date NOT NULL, `status` varchar(12) NOT NULL, `created_at` datetime(6) NOT NULL);
--
-- Create model Material
--
CREATE TABLE `construction_material` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `name` varchar(200) NOT NULL, `quantity` numeric(12, 2) NOT NULL, `unit` varchar(5) NOT NULL, `unit_price` numeric(12, 2) NOT NULL, `created_at` datetime(6) NOT NULL, `project_id` bigint NOT NULL);
--
-- Create model Expense
--
CREATE TABLE `construction_expense` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `title` varchar(200) NOT NULL, `category` varchar(12) NOT NULL, `amount` numeric(14, 2) NOT NULL, `date` date NOT NULL, `description` longtext NOT NULL, `created_at` datetime(6) NOT NULL, `project_id` bigint NOT NULL);
--
-- Create model Task
--
CREATE TABLE `construction_task` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `title` varchar(200) NOT NULL, `description` longtext NOT NULL, `due_date` date NOT NULL, `status` varchar(12) NOT NULL, `created_at` datetime(6) NOT NULL, `project_id` bigint NOT NULL);
--
-- Create model Worker
--
CREATE TABLE `construction_worker` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `first_name` varchar(100) NOT NULL, `last_name` varchar(100) NOT NULL, `position` varchar(20) NOT NULL, `phone` varchar(20) NOT NULL, `created_at` datetime(6) NOT NULL, `project_id` bigint NULL);
ALTER TABLE `construction_material` ADD CONSTRAINT `construction_materia_project_id_35abdbfa_fk_construct` FOREIGN KEY (`project_id`) REFERENCES `construction_project` (`id`);
ALTER TABLE `construction_expense` ADD CONSTRAINT `construction_expense_project_id_a1f91fa5_fk_construct` FOREIGN KEY (`project_id`) REFERENCES `construction_project` (`id`);
ALTER TABLE `construction_task` ADD CONSTRAINT `construction_task_project_id_0621cd71_fk_construction_project_id` FOREIGN KEY (`project_id`) REFERENCES `construction_project` (`id`);
ALTER TABLE `construction_worker` ADD CONSTRAINT `construction_worker_project_id_e004d84b_fk_construct` FOREIGN KEY (`project_id`) REFERENCES `construction_project` (`id`);
