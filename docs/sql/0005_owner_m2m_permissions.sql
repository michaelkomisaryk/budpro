--
-- Change Meta options on expense
--
-- (no-op)
--
-- Change Meta options on worklog
--
-- (no-op)
--
-- Add field owner to project
--
ALTER TABLE `construction_project` ADD COLUMN `owner_id` integer NULL , ADD CONSTRAINT `construction_project_owner_id_c993b7b2_fk_auth_user_id` FOREIGN KEY (`owner_id`) REFERENCES `auth_user`(`id`);
--
-- Add field materials to task
--
CREATE TABLE `construction_task_materials` (`id` bigint AUTO_INCREMENT NOT NULL PRIMARY KEY, `task_id` bigint NOT NULL, `material_id` bigint NOT NULL);
--
-- Add field owner to worker
--
ALTER TABLE `construction_worker` ADD COLUMN `owner_id` integer NULL , ADD CONSTRAINT `construction_worker_owner_id_5cd616a0_fk_auth_user_id` FOREIGN KEY (`owner_id`) REFERENCES `auth_user`(`id`);
--
-- Alter field phone on worker
--
-- (no-op)
--
-- Alter field hours on worklog
--
-- (no-op)
ALTER TABLE `construction_task_materials` ADD CONSTRAINT `construction_task_materials_task_id_material_id_3d2d8ca2_uniq` UNIQUE (`task_id`, `material_id`);
ALTER TABLE `construction_task_materials` ADD CONSTRAINT `construction_task_ma_task_id_f35a0e74_fk_construct` FOREIGN KEY (`task_id`) REFERENCES `construction_task` (`id`);
ALTER TABLE `construction_task_materials` ADD CONSTRAINT `construction_task_ma_material_id_6e38b053_fk_construct` FOREIGN KEY (`material_id`) REFERENCES `construction_material` (`id`);
