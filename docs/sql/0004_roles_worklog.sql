--
-- Add field assignee to task
--
ALTER TABLE `construction_task` ADD COLUMN `assignee_id` bigint NULL , ADD CONSTRAINT `construction_task_assignee_id_058f4d9a_fk_construction_worker_id` FOREIGN KEY (`assignee_id`) REFERENCES `construction_worker`(`id`);
--
-- Add field hourly_rate to worker
--
ALTER TABLE `construction_worker` ADD COLUMN `hourly_rate` numeric(8, 2) DEFAULT 0 NOT NULL;
ALTER TABLE `construction_worker` ALTER COLUMN `hourly_rate` DROP DEFAULT;
--
-- Add field user to worker
--
ALTER TABLE `construction_worker` ADD COLUMN `user_id` integer NULL UNIQUE , ADD CONSTRAINT `construction_worker_user_id_8e5f0483_fk_auth_user_id` FOREIGN KEY (`user_id`) REFERENCES `auth_user`(`id`);
--
-- Create model WorkLog
--
CREATE TABLE `construction_worklog` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `date` date NOT NULL, `hours` numeric(5, 2) NOT NULL, `comment` varchar(255) NOT NULL, `rate` numeric(8, 2) NOT NULL, `created_at` datetime(6) NOT NULL, `task_id` bigint NULL, `worker_id` bigint NOT NULL);
ALTER TABLE `construction_worklog` ADD CONSTRAINT `construction_worklog_task_id_230a1524_fk_construction_task_id` FOREIGN KEY (`task_id`) REFERENCES `construction_task` (`id`);
ALTER TABLE `construction_worklog` ADD CONSTRAINT `construction_worklog_worker_id_866a6a66_fk_construct` FOREIGN KEY (`worker_id`) REFERENCES `construction_worker` (`id`);
