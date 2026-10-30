import time

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class ChromeCase(StaticLiveServerTestCase):
    """Базовий клас: відкриває видиме вікно Chrome для UI-тестів."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        options = Options()
        cls.browser = webdriver.Chrome(options=options)
        cls.browser.set_window_rect(x=40, y=40, width=1280, height=780)
        cls.wait = WebDriverWait(cls.browser, 10)

    @classmethod
    def tearDownClass(cls):
        cls.browser.quit()
        super().tearDownClass()

    def open(self, path):
        self.browser.get(self.live_server_url + path)
        time.sleep(0.6)

    def show(self, element):
        self.browser.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});",
            element,
        )
        time.sleep(0.2)

    def fill(self, name, value):
        field = self.wait.until(EC.presence_of_element_located((By.NAME, name)))
        self.show(field)
        field_type = (field.get_attribute("type") or "").lower()
        if field_type == "date":
            self.browser.execute_script(
                "arguments[0].value = arguments[1];"
                "arguments[0].dispatchEvent(new Event('input', {bubbles: true}));"
                "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
                field,
                value,
            )
        else:
            field.clear()
            field.send_keys(value)
        time.sleep(0.3)

    def submit(self, label=None):
        if label:
            button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, f"//button[contains(., '{label}')]"))
            )
        else:
            button = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "form button.btn"))
            )
        self.show(button)
        button.click()
        time.sleep(1.0)

    def login(self, username, password):
        self.open("/login/")
        self.fill("username", username)
        self.fill("password", password)
        self.submit("Увійти")
