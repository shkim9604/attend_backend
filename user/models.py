from django.db import models

# Create your models here.

#유저
class User(models.Model):
    name = models.CharField(max_length=20)
    employee_number = models.IntegerField()
    phone_number = models.CharField(max_length=20)
    department_code = models.IntegerField(default=0)
    def __str__(self):
        return  f'{self.name} - {self.department_code} - {self.id_number}'

    class Meta:
        ordering = ['-id_number']
        db_table = "users"

class Checked_User(models):
    name = models.CharField(max_length=20)
    employee_number = models.IntegerField()
    phone_number = models.CharField(max_length=20)
    department_code = models.IntegerField(default=0)

    def __str__(self):
        return  f'{self.name} - {self.department_code} - {self.id_number}'

    class Meta:
        ordering = ['-id_number']
        db_table = "checked_user"