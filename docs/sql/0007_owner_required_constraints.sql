--
-- Alter field owner on project
--
ALTER TABLE `construction_project` DROP FOREIGN KEY `construction_project_owner_id_c993b7b2_fk_auth_user_id`;
ALTER TABLE `construction_project` MODIFY `owner_id` integer NOT NULL;
ALTER TABLE `construction_project` ADD CONSTRAINT `construction_project_owner_id_c993b7b2_fk_auth_user_id` FOREIGN KEY (`owner_id`) REFERENCES `auth_user` (`id`);
--
-- Alter field owner on worker
--
ALTER TABLE `construction_worker` DROP FOREIGN KEY `construction_worker_owner_id_5cd616a0_fk_auth_user_id`;
ALTER TABLE `construction_worker` MODIFY `owner_id` integer NOT NULL;
ALTER TABLE `construction_worker` ADD CONSTRAINT `construction_worker_owner_id_5cd616a0_fk_auth_user_id` FOREIGN KEY (`owner_id`) REFERENCES `auth_user` (`id`);
--
-- Create constraint uniq_catalog_name_unit on model catalogitem
--
ALTER TABLE `construction_catalogitem` ADD CONSTRAINT `uniq_catalog_name_unit` UNIQUE (`name`, `unit`);
--
-- Create constraint uniq_project_owner_name on model project
--
ALTER TABLE `construction_project` ADD CONSTRAINT `uniq_project_owner_name` UNIQUE (`owner_id`, `name`);
