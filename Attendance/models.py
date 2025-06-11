from django.db import models
from django.utils import timezone
# Create your models here.

class Attendance(models.Model):
    name = models.CharField(max_length=20)
    employee_number = models.IntegerField()
    check_date = models.DateField()
    business_start_time = models.TimeField(default="00:00")
    check_in_time = models.TimeField(default="00:00")
    check_out_time = models.TimeField(default="00:00")
    business_end_time = models.TimeField(default="00:00")
    business_start_place = models.CharField(default="")
    check_in_place_name = models.CharField(max_length=20,default="")
    check_out_place_name = models.CharField(max_length=20,default="")
    business_end_place = models.CharField(max_length=20,default="")
    check_in_location = models.CharField(max_length=30,default="")
    check_out_location = models.CharField(max_length=30,default="")
    check_in_type = models.CharField(max_length=20,default="")
    check_out_type = models.CharField(max_length=20,default="")
    created_time = models.TimeField(default=timezone.now)

    def __str__(self):
        return f"{self.name} - {self.check_date} - {self.check_in_time} - {self.check_out_time}"

    class Meta:
        db_table = "attendance"