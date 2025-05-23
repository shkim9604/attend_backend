from django.shortcuts import render
from django.utils import timezone
from django.http import JsonResponse
from .models import Attendance
import json

# Create your views here.

def check_in(request):
    if request.method == "POST":
        data = json.loads(request.body)
        name = data.get('name','')
        employee_number = data.get('employee_number','')
        check_in_place_name = data.get('place_name','')
        check_in_location = data.get('location','')
        check_date = data.get('check_date','')
        check_in_time = data.get('check_time','')
        #날짜,시간 형태변경
        check_date = datetime.strptime(check_date,"%Y-%m-%d").date()
        check_in_time = datetime.strptime(check_in_time, "%H:%M").time()
        #출근데이터생성
        Attendance.objects.create(
            name = name,
            employee_number = employee_number,
            check_date = check_date,
            check_in_time = check_in_time,
            check_in_place_name = check_in_place_name,
            check_in_location = check_in_location
        )

        #출근메시지 반환
        return JsonResponse({'success': True, 'message': f'{check_in_time}에 출근처리 되었습니다.'})


def check_out(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        name = data.get('name','')
        employee_number = data.get('employee_number','')
        check_out_place_name = data.get('place_name','')
        check_out_location = data.get('location','')
        check_date = data.get('check_date','')
        check_out_time = data.get('check_time','')
        #날짜,시간 형태변경
        check_date = datetime.strptime(check_date,"%Y-%m-%d").date()
        check_out_time = datetime.strptime(check_out_time, "%H:%M").time()
        #최근 출근데이터 찾기
        recent_attendance = Attendance.objects.filter(name=name, employee_number=employee_number).order_by("-check_date",'-create_time')
        recent_attendance = recent_attendance[0]
        #최근 출근데이터에 퇴근데이터 넣기
        recent_attendance.check_out_time = check_out_time
        recent_attendance.check_out_place_name = check_out_place_name
        recent_attendance.check_out_location = check_out_location
        recent_attendance.save()
        return JsonResponse({'success': True, 'message': f'{check_out_time}에 퇴근처리가 되었습니다.'})