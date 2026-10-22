# PyMySQL працює як драйвер MySQLdb: так не потрібно збирати mysqlclient на Windows
import pymysql

pymysql.install_as_MySQLdb()
