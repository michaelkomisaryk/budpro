"""Два автоматизовані UI-тести Selenium (відкривають Chrome)."""
import time
from datetime import date, timedelta

from django.contrib.auth.models import User
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

from .access import DIRECTOR_GROUP, sync_roles
from .chrome import ChromeCase
from .models import Project


class RegistrationChromeTests(ChromeCase):
    def test_registration_creates_a_director(self):
        """TC: реєстрація директора — акаунт у групі «Директор» і відкривається кабінет."""
        sync_roles()
        self.open("/register/")
        self.fill("first_name", "Ольга")
        self.fill("last_name", "Мазур")
        self.fill("username", "newdirector_ui")
        self.fill("email", "olga.ui@example.com")
        self.fill("password1", "Str0ng-pass-77")
        self.fill("password2", "Str0ng-pass-77")
        self.submit("Зареєструватися")

        # RegisterView одразу логінить і веде на головну
        self.assertIn("Головна", self.browser.page_source)
        self.assertIn("Акаунт створено", self.browser.page_source)

        user = User.objects.get(username="newdirector_ui")
        self.assertTrue(user.groups.filter(name=DIRECTOR_GROUP).exists())
        self.assertEqual(user.first_name, "Ольга")
        self.assertEqual(user.email, "olga.ui@example.com")
        time.sleep(1.5)


class ProjectChromeTests(ChromeCase):
    def setUp(self):
        sync_roles()
        self.boss = User.objects.create_user("boss_ui", password="pw12345678")
        from django.contrib.auth.models import Group

        self.boss.groups.add(Group.objects.get(name=DIRECTOR_GROUP))
        super().setUp()

    def test_director_creates_a_project(self):
        """TC: директор логіниться, створює проєкт — запис з'являється в списку і в БД."""
        self.login("boss_ui", "pw12345678")
        self.open("/projects/new/")

        start = date.today().isoformat()
        end = (date.today() + timedelta(days=60)).isoformat()
        self.fill("name", "ЖК Selenium-тест")
        self.fill("address", "м. Львів, вул. Тестова 1")
        self.fill("description", "Проєкт створений автотестом Selenium.")
        self.fill("budget", "250000")
        self.fill("start_date", start)
        self.fill("end_date", end)
        Select(self.browser.find_element(By.NAME, "status")).select_by_value("active")
        self.submit("Зберегти")

        self.assertTrue(
            Project.objects.filter(name="ЖК Selenium-тест", owner=self.boss).exists(),
        )
        project = Project.objects.get(name="ЖК Selenium-тест", owner=self.boss)
        self.assertEqual(project.address, "м. Львів, вул. Тестова 1")
        self.assertEqual(str(project.budget), "250000.00")

        self.open("/projects/")
        self.assertIn("ЖК Selenium-тест", self.browser.page_source)
        time.sleep(1.5)
