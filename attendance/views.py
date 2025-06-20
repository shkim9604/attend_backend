from django.shortcuts import render
from django.utils import timezone
from django.http import JsonResponse
from django.http import HttpResponse
from datetime import time, timedelta
import json
#MDB파일 관련
from django.conf import settings
import subprocess
import os
from io import StringIO
import pandas as pd
#출퇴근관련
from django.db.models import Q
#출퇴근 엑셀
from openpyxl.utils import get_column_letter
from urllib.parse import quote
import io
#모델가져오기
from .models import Attendance
from ..user.models import User
# Create your views here.

#MDB파일 출근데이터 기록하기
def mdbfile_record(request):
    if request.method == 'POST':
        if 'file' not in request.FILES:
            return JsonResponse({'success':False, 'message': '파일이 없습니다.'})

        #파일가져오기
        uploaded_file = request.FILES['file']

        #파일 저장 경로 설정
        save_path = os.path.join(settings.MEDIA_ROOT, uploaded_file.name)

        #파일저장
        with open(save_path, 'wb+') as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)

        print(f"파일이 {save_path}에 저장되었습니다.")

        try:
            # 카드번호와 사원번호가 매칭된 엑셀파일 가져오기
            excel_path = os.path.join(settings.MDEIA_ROOT, 'card_idnumber.xlsx')
            #엑셀파일에서 데이터 읽기
            excel_df = pd.read_excel(excel_path, engine='openpyxl')

            #MDB파일 CSV로 변환
            table_name = 'attendancetime'
            command = ['mdb-export', save_path, table_name]
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            if result.returncode != 0:
                print(f"Error: {result.stderr}")
                return JsonResponse({'success': False, 'message': f'명령 실행 중 오류 발생: {result.stderr}'})

            #데이터 프레임 읽기
            data = StringIO(result.stdout)
            df = pd.read_csv(data)

            #필요한 필드 선택
            required_fields = ['e_date', 'e_time', 'e_id', 'e_name', 'e_mode']
            #필드 누락확인
            for field in required_fields:
                if field not in df.columns:
                    return JsonResponse({'success': False, 'message': f'필드{field}가 누락되었습니다.'})

            #데이터프레임에서 필요한 열 추출
            df_filterd = df[required_fields].copy()
            three_days_ago = datetime.now() - timedelta(days=3)
            three_days_ago_str = three_days_ago.date()

            #날짜와 시간을 변환해서 저장
            df_filterd.loc[:,'e_date'] = pd.to_datetime(df_filterd['e_date'],format="%Y%m%d",errors='coerce').dt.date
            #삽입하는 데이터를 현재날짜에서 3일전까지의 데이터만 넣는걸로 설정 예) 현날짜가 11일이면 8일부터 삽입
            df_filterd = df_filterd[df_filterd['e_date'] >= three_days_ago_str]
            #시간을 분까지만 표시
            df_filterd.loc[:,'e_time'] = pd.to_datetime(df_filterd['e_time'], format="%H%M%S",errors='coerce').dt.rount('min').dt.time

            #결측값 제거
            df_filterd.dropna(subset=['e_date','e_time'], inplace=True)

            #날짜,시간을 기준으로 정렬
            df_filterd = df_filterd.sort_values(by=['e_date','e_time'],ascending=[True, True])

            for i, row in df_filterd.iterrows():
                #e_name이 Nan이면 넘어가기
                if pd.isna(row['e_name']):
                    continue
                check_date = row['e_date']
                employee_number = row['e_id']
                name = row['e_name']
                check_time = row['e_time']
                check_mode = row['e_mode']
                #엑셀에서 카드번호와 매칭되는 사원번호 가져오기
                matching_rows = excel_df[excel_df['카드ID'] == employee_number]
                if not matching_rows.empty:
                    employee_number = matching_rows['사원번호'].values[0]

                #등록시간 변환
                check_combine_time = datetime.combine(check_date, check_time)

                if check_mode == 1 or check_mode == 2:
                    if check_mode == 1:
                        #출근생성
                        attendance_record = Attendance.objects.filter(
                            name = name,
                            employee_number = employee_number,
                            check_date = check_date,
                            check_in_time = check_time,
                        )
                        if not attendance_record.exists():
                            #check_date의 데이터가 없기에 새로 생성
                            #데이터조회떄 created_time을 참고하기떄문에 created_time에 카드가 찍힌날짜와 시간 대입
                            Attendance.objects.create(
                                name = name,
                                employee_number = employee_number,
                                check_date = check_date,
                                check_in_time = check_time,
                                check_in_place_name = "본사",
                                check_in_location = "본사",
                                check_in_type = "카드",
                                created_time = check_combine_time
                            )
                        else:
                            #이미 생성된 데이터이기에 넘어갑니다.
                            continue
                    elif check_mode == 2:
                        attendance_record = Attendance.objects.filter(
                            name = name,
                            employee_number = employee_number,
                            check_date = check_date,
                        )
                        if attendance_record.exists():
                            #해당날짜의 출근데이터가 있음
                            #여러개인지 확인
                            if len(attendance_record) >= 2:
                                match_attendance = attendance_record.filter(check_out_time = check_time).first()
                                if match_attendance:
                                    continue
                                else:
                                    #출근기록이 2개이상이므로 정렬한후 최근값을 가져온다
                                    recent_attendance = None
                                    for i in match_attendance.order_by('-check_in_time'):
                                        if i.check_in_time < check_time:
                                            recent_attendance = i
                                            break
                                    if recent_attendance.business_start_time == time(0,0,0):
                                        #출장출발기록이 없으면 정상퇴근처리
                                        recent_attendance.check_out_time = check_time
                                        recent_attendance.check_out_place_name = "본사"
                                        recent_attendance.check_out_location = "본사"
                                        recent_attendance.check_type = "카드"
                                        recent_attendance.save()
                                    else:
                                        #출장을하고 카드로 퇴근을 했기에 출장복귀에 퇴근기록을 넣음
                                        recent_attendance.check_out_time = check_time
                                        recent_attendance.business_end_time = check_time
                                        recent_attendance.check_out_place_name = "본사"
                                        recent_attendance.check_out_location = "본사"
                                        recent_attendance.check_type = "카드"
                                        recent_attendance.save()
                            else:
                                #해당날짜에 출퇴근기록이 1개라면 바로값을 넣는다.
                                recent_attendance = recent_attendance[0]
                                if recent_attendance.business_start_time == time(0, 0, 0):
                                    #출장출발이 없는 정상퇴근
                                    recent_attendance.check_out_time = check_time
                                    recent_attendance.check_out_place_name = "본사"
                                    recent_attendance.check_out_location = "본사"
                                    recent_attendance.check_type = "카드"
                                    recent_attendance.save()
                                else:
                                    #출장출발이 있어 복귀시간에 퇴근시간을 넣음
                                    recent_attendance.check_out_time = check_time
                                    recent_attendance.business_end_time = check_time
                                    recent_attendance.check_out_place_name = "본사"
                                    recent_attendance.check_out_location = "본사"
                                    recent_attendance.check_out_type = "카드"
                                    recent_attendance.save()
                else:
                    #출근은 1 퇴근은 2 그외에는 쓸모없으니 패스한다
                    continue

            return JsonResponse({'success': True, 'message': 'MDB파일로 출퇴근 처리 완료'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'MDB 파일 처리하는중 오류발생'})
    else:
        return JsonResponse({'success': False, 'message': "잘못된 요청입니다."})






#출장출발
def business_start(request):
    if request.method == "POST":
        data = json.loads(request.body)
        name = data.get('name','')
        employee_number = data.get('employee_number','')
        check_date = data.get('check_date','')
        business_start_time = data.get('buiness_start_time','')
        business_start_place= data.get('place_name','')
        #날짜,시간 변형
        check_date = datetime.strptime(check_date,"%Y-%m-%d").date()
        business_start_time = datetime.strptime(business_start_time, "%H:%M").time()
        Attendance.objects.create(
            name = name,
            employee_number = employee_number,
            check_date = check_date,
            business_start_time = business_start_time,
            business_start_place = business_start_place,
        )
        return JsonResponse({'success': True, 'message': f'{business_start_time}에 출장출발 처리 되었습니다.'})
    else:
        return JsonResponse({'success': False, 'message': "잘못된 요청입니다."})
#출장복귀
def business_end(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        name = data.get('name','')
        employee_number = data.get('employee_number', '')
        check_date = data.get('check_date', '')
        business_end_time = data.get('business_end_time','')
        business_end_place = data.get('place_name','')
        #날짜,시간 형태변경
        check_date = datetime.strptime(check_date,"%Y-%m-%d").date()
        business_end_time = datetime.strptime(business_end_time, "%H:%M").time()
        #가장최근기록에 복귀 데이터 넣기
        recent_attendance = Attendance.objects.filter(name=name,employee_number=employee_number).order_by('-check_date','-created_time').first()
        #예)17일출장출발 18일 새벽복귀
        if recent_attendance.check_date != check_date:
            if recent_attendance.check_out_time == time(0,0,0):
                #최근기록에 퇴근이 없을시 퇴근을 먼저하라는 메시지를 반환한다.
                return JsonResponse({'success': False, 'message': '퇴근처리가 되있지않습니다.\n퇴근부터 해주시길 바랍니다.'})
            else:
                #퇴근이 되어있을경우 그 기록에 복귀기록을 씌운다.
                #날짜가 다른복귀이기에 퇴근처럼 24초를 더해서 처리한다.
                business_end_time = datetime.combine(check_date,business_end_time) + timedelta(seconds=24)
                business_end_time = business_end_time.time()
                recent_attendance.business_end_time = business_end_time
                recent_attendance.business_end_place = business_end_place
                recent_attendance.save()
                return JsonResponse({'success': True, 'message': f'{business_end_time}에 출장복귀처리가 되었습니다.'})
        else:
            #날짜가 같으면 당일 출장복귀이기에 최근기록에 복귀기록을 씌운다.
            if recent_attendance.check_out_time == time(0,0,0):
                return JsonResponse({'success': False, 'message': '퇴근처리가 되있지않습니다.\n퇴근부터 해주시길 바랍니다.'})
            if recent_attendance.business_end_time != time(0,0,0):
                #최근기록의 복귀시간이 00:00이 아니면 복귀를 했기에 복귀처리된시간을 반환해준다.
                return JsonResponse({'success': False, 'message': f'{recent_attendance.check_date}일 {recent_attendance.business_end_time}자로 복귀처리가되었습니다.'})
            #두조건을 통과하면 당일복귀처리를 한다.
            recent_attendance.business_end_time = business_end_time
            recent_attendance.business_end_place = business_end_place
            recent_attendance.save()
            return JsonResponse({'success': True, 'message': f'{business_end_time}에 출장복귀 처리 되었습니다.'})
    else:
        return JsonResponse({'success': False, 'message': "잘못된 요청입니다."})

#출근
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
        #출장출발유무 체크
        business_check = Attendance.objects.filter(name=name,employee_number=employee_number).order_by(-'created_time').first()
        if business_check.business_start != time(0,0,0):
            print("출장기록이 있으므로 출퇴근 기록을 확인합니다.")
            if business_check_in_time != time(0,0,0) or business_check.check_out_time != time(0,0,0):
                print("최근기록에 출장출발이 있고 출근이나 퇴근이 기록되어있으므로 새로운출퇴근기록을 만듭니다.")
                Attendance.objects.create(
                    name = name,
                    employee_number = employee_number,
                    check_date = check_date,
                    check_in_time = check_in_time,
                    check_in_place_name = check_in_place_name,
                    check_in_location = check_in_location,
                    check_in_type = "웹"
                )
                return JsonResponse({'success': True, 'message': f'{check_in_time}에 출근처리 되었습니다.'})
            else:
                print("최근기록에 츨징츨발기록이 있고 출퇴근기록이 없으므로 출장출발기록에 출근을 넣는다.")
                business_check.check_in_time = check_in_time
                business_check.check_in_place_name = check_in_place_name
                business_check.check_in_location = check_in_location
                business_check.check_in_type = "웹"
                business_check.save()
                return JsonResponse({'success': True, 'message': f'{check_in_time}에 출근처리 되었습니다.'})
        #출근데이터생성
        else:
            print("출장출발기록이 없다면 새 데이터를 만듭니다.")
            Attendance.objects.create(
                name = name,
                employee_number = employee_number,
                check_date = check_date,
                check_in_time = check_in_time,
                check_in_place_name = check_in_place_name,
                check_in_location = check_in_location,
                check_in_type = "웹"
            )
            #출근메시지 반환
            return JsonResponse({'success': True, 'message': f'{check_in_time}에 출근처리 되었습니다.'})
    else:
        return JsonResponse({'success': False, 'message': "잘못된 요청입니다."})
#퇴근
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
        recent_attendance = Attendance.objects.filter(name=name, employee_number=employee_number).order_by("-check_date",'-created_time').first()

        #출퇴근데이터가 없는경우
        if not recent_attendance:
            Attendance.objects.create(
                name = name,
                employee_number = employee_number,
                check_date = check_date,
                check_out_time = check_out_time,
                check_out_place_name = check_out_place_name,
                check_out_location = check_out_location,
                check_out_type = "웹"
            )
            return JsonResponse({'success': True, 'message': f'{check_out_time}에 퇴근처리가 되었습니다.'})

        if recent_attendance and recent_attendance.business_end_time == time(0,0,0):
            #최근기록과 퇴근날짜가 다른지 확인
            if recent_attendance.check_date != check_date:
                #날짜가 다르다면 새벽에 퇴근을 의미하는것이고 퇴근시간이 00인지 확인
                if recent_attendance.check_out_time == time(0, 0, 0):
                    # 24시가넘어가는 퇴근을 구분을 위해 초단위에 24초를 더해서 저장한다.
                    check_out_time = datetime.combine(check_date, check_out_time) + timedelta(seconds=24)
                    check_out_time = check_out_time.time()
                    recent_attendance.check_out_time = check_out_time
                    recent_attendance.check_out_place_name = check_out_place_name
                    recent_attendance.check_out_location = check_out_location
                    recent_attendance.check_out_type = "웹"
                    recent_attendance.save()
                    check_out_time = check_out_time.strftime("%H:%M")
                    return JsonResponse({'success': True, 'message': f'{check_out_time}에 퇴근처리 되었습니다.'})
                else:
                    # 퇴근기록날짜와 최근기록날짜가 다르고 최근기록에 퇴근기록이 있을경우 출근을누락했거나 잘못누른경우을 뜻함
                    Attendance.objects.create(
                        name=name,
                        employee_number=employee_number,
                        check_date=check_date,
                        check_out_time=check_out_time,
                        check_out_place_name=check_out_place_name,
                        check_out_location=check_out_location,
                        check_out_type="웹"
                    )
                    return JsonResponse({'success': True, 'message': f'{check_out_time}에 퇴근처리 되었습니다.'})
            else:
                # 최근기록날짜와 퇴근기록날짜가 같은거는 당일퇴근이기에 최근기록에 퇴근기록을 씌우면 된다.
                recent_attendance.check_out_time = check_out_time
                recent_attendance.check_out_place_name = check_out_place_name
                recent_attendance.check_out_location = check_out_location
                recent_attendance.check_out_type = "웹"
                recent_attendance.save()
                return JsonResponse({'success': True, 'message': f'{check_out_time}에 퇴근처리가 되었습니다.'})
        else:
            #출장복귀를완료한상태이기때문에 새로운 출퇴근데이터를 생성한다.
            Attendance.objects.create(
                name=name,
                employee_number=employee_number,
                check_date=check_date,
                check_out_time=check_out_time,
                check_out_place_name=check_out_place_name,
                check_out_location=check_out_location,
                check_out_type = "웹"
            )
            return JsonResponse({'success': True, 'message': f'{check_out_time}에 퇴근처리가 되었습니다.'})
    else:
        return JsonResponse({'success': False, 'message': "잘못된 요청입니다."})

#직원 자기출퇴근조회
def employee_self_attend_check(request):
    if request.method == "POST":
        data = json.loads(request.body)
        name = data.get('name','')
        employee_number = data.get('employee_number')
        code = User.objects.filter(name=name, employee_number=employee_number).first()
        code = code.department_code
        end_date =  timezone.now(),date() + timedelta(days=1)
        start_date = end_date - timedelta(days=7)

        #코드를 통해 임직원의 직책을 알고 직책에 따라 조회할수있는 범위가 달라짐
        #예) 사업1팀 팀장은 팀장본인것은 물런이고 사업팀 직원들의 출퇴근도 조회가능
        if code == 200:
            query = Q(department_code__in=[200,210,211,300])
        elif code == 210:
            query = Q(department_code__in=[210,211])
        elif code == 300:
            query = Q(department_code__in=[300,310,311,320,321])
        elif code == 310:
            query = Q(department_code__in=[310,311])
        elif code == 320:
            query = Q(department_code__in=[320,321])
        elif code == 400:
            query = Q(department_code_in=[400,410,411])
        elif code == 410:
            query = Q(department_code_in=[410,411])
        else:
            query = Q()#조건이 없으면 빈쿼리
        excluded_fields = ['business_start_place', 'business_end_place']
        data = []
        if query:
            users = User.objects.filter(query)
            for user in users:
                attendance_data = Attendance.objects.filter(name=user.name,employee_number=user.employee_number,check_date__range=[start_date, end_date]).order_by('-check_date', '-created_time').values()
                for record in attendance_data:
                    filtered_record = {}
                    for k, v in record.items():
                        if k not in excluded_fields:
                            filtered_record[k] = v
                    data.append(filtered_record)
        else:
            attendance_data = Attendance.objects.filter(check_date__range=[start_date, end_date]).order_by('-check_date','-created_time').values()
            for record in attendance_data:
                filterd_record = {}
                for k,v in record.items():
                    if k not in excluded_fields:
                        filterd_record[k] = v
                data.append(filterd_record)

        return JsonResponse(data,safe=False)
    else:
        return JsonResponse({'success': False, 'message': '잘못된 요청입니다.'})

#관리자 출퇴근조회
def admin_get_employee_attendance(request):
    if request.method == 'GET':
        end_date = timezone.now().date() + timedelta(days=1)
        start_date = end_date - timedelta(days=7)
        attendance_data = Attendance.objects.filter(check_date__range=[start_date,end_date]).order_by('-created_time').values()
        return JsonResponse(list(attendance_data),safe=False)
    else:
        return JsonResponse({'success': False, 'message': '잘못된 요청입니다.'})

#관리자 직원 출퇴근상세조회
def admin_get_employee_attendance_detail(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        name = data.get('name','')
        start_date = data.get('start_date','')
        end_date = data.get('end_date','')
        if start_date == "" and end_date == "":
            #시작날짜와 끝날짜가 비어있으므로 7일치의 데이터를 가져온다.
            end_date = timezone.now().date() + timedelta(days=1)
            start_date = end_date - timedelta(days=7)
            if name == "전직원":
                attendance_data = Attendance.objects.filter(check_date__range=[start_date,end_date]).order_by('-created_time').values()
                return JsonResponse(list(attendance_data), safe=False)
            else:
                #이름이 있으니 해당직원의 데이터를 가져온다.
                attendance_data = Attendance.objects.filter(name=name, check_date__range=[start_date, end_date]).order_by('-created_time').values()
                return JsonResponse(list(attendance_data), safe=False)
        else:
            #날짜가 있으므로 해당날짜에 해당하는 데이터를 가져온다.
            if name == "전직원":
                attendance_data = Attendance.objects.filter(check_date__range=[start_date,end_date]).order_by('-created_time').values()
                return JsonResponse(list(attendance_data), safe=False)
            attendance_data = Attendance.objects.filter(name=name, check_date__range=[start_date, end_date]).order_by('-created_time').values()
            return JsonResponse(list(attendance_data), safe=False)
    else:
        return JsonResponse({'success': False, 'message': '잘못된 요청입니다.'})


#직원 자기출퇴근 기록 다운로드
def download_employee_attendance(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        name = data.get('name','')
        employee_number = data.get('employee_number','')
        start_date = data.get('start_date','')
        end_date = data.get('end_date','')
        attendance_data = Attendance.objects.filter(
            name = name,
            employee_number = employee_number,
            check_date__range=[start_date, end_date]
        ).values(
            'name', 'employee_number', 'check_date',
            'business_start_time', 'check_in_time', 'check_out_time','buisness_end_time',
            'check_in_place_name', 'check_in_location', 'check_out_place_name', 'check_out_location',
            'check_in_type','check_out_type'
        )
        #데이터 변환
        df = pd.DataFrame(attendance_data)
        df['check_date'] = pd.to_datetime(df['check_date']).dt.date

        #영어로 되어있는 이름 한국어로 변경
        df.columns = ["이름", "사원번호", "날짜", "출장출발", "출근시간", "퇴근시간", "출장복귀",
                      "출근장소", "퇴근장소", "출근위치", "퇴근위치", "출근방식", "퇴근방식"]
        df["조기출근"] = ""
        df["연장근무"] = ""

        #시간값 객체로 변환
        def clean_time(value):
            try:
                #시간을 pandas에서 처리 ,잘못된값은 NaT로 처리
                return pd.to_datetime(value, format="%H:%M:%S", errors='coerce').time()
            except Exception as e:
                print(f"Error parsing time: {value}, Error: {e}")
                return None

        #출근시간 퇴근시간 클리닝
        df['출근시간'] = df['출근시간'].apply(clean_time)
        df['퇴근시간'] = df['퇴근시간'].apply(clean_time)

        #조기출근 연장근무 계산
        def calculate_remarks(row):
            #조기출근 계산
            if pd.notnull(row['출근시간']) and row['출근시간'] != datetime.strptime("00:00:00", "%H:%M:%S").time():
                check_in_time = datetime.combine(datetime.today(), row['출근시간'])
                early_check_time = datetime.combine(datetime.today(), datetime.strptime("08:00:00", "%H:%M").time())
                if check_in_time >= "08:00:00":
                    pass
                if check_in_time < early_check_time:
                    early_minutes = (early_check_time - check_in_time).seconds // 60
                    row["조기출근"] = f"{early_minutes}분"

            #연장근무 계산
            if pd.notnull(row['퇴근시간']):
                check_out_time = datetime.combine(datetime.today(), row['퇴근시간'])
                late_check_time = datetime.combine(datetime.today(), datetime.strptime('19:00',"%H:%M").time())
                if check_out_time > late_check_time:
                    late_minutes = (check_out_time - late_check_time).seconds // 60
                    row["연장근무"] = f"{late_minutes}분"

            return row

        df = df.apply(calculate_remarks, axis=1)

        #엑셀파일로 변환
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            #날짜 기준으로 월별로 데이터를 그룹화 각각시트에 기록
            for month, group in df.groupby(df['날짜'].apply(lambda x: x.strftime("%Y-%m"))):
                group.to_excel(writer, index=False, sheet_name=month)

                #엑셀 워크북과 시트 가져오기
                worksheet = writer.sheets[month]

                #열 너비 조정
                for col in worksheet.columns:
                    max_length = 0
                    column = col[0].column_letter
                    for cell in col:
                        try:
                            if cell.value:
                                max_length = max(max_length, len(str(cell.value)))
                        except:
                            pass
                    width = (max_length + 4) #너비 조정(여유공간)
                    worksheet.column_dimensions[column].width = width

        output.seek(0)

        #파일이름설정
        filename = quote(f"출퇴근기록_{datetime.now().strftime('%Y%m%d')}.xlsx")
        response = HttpResponse(output, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename*=UTF-8\'\'{filename}'

        return response


#전직원 출퇴근기록 엑셀 다운로드
def download_all_employee_attendance(request):
    attendance_data = Attendance.objects.all().values(
        'name','employee_number', 'check_date',
        'buiness_start_time', 'check_in_time', 'check_out_time', 'business_end_time',
        'buiness_start_'
    )

    #데이터 변환
    df = pd.DataFrame(attendance_data)
    df['check_date'] = pd.to_datetime(df['check_date']).dt.date

    #한국어변경
    df.colums = ['이름', '사원번호', '날짜', '출장출발', '출근시간', '퇴근시간', '출장복귀',
                 '출근장소' ,'퇴근장소' ,'출근위치', '퇴근위치', '출근방식', '퇴근방식']
    df['조기출근'] = ''
    df['연장근무'] = ''

    # 데이터 클리닝 함수
    def clean_time(value):
        try:
            # 시간을 pandas에서 자동으로 처리, 잘못된 값은 NaT로 처리
            return pd.to_datetime(value, format='%H:%M:%S', errors='coerce').time()
        except Exception as e:
            print(f"Error parsing time: {value}, Error: {e}")
            return None

    # 출근 시간과 퇴근 시간을 클리닝
    df['출근시간'] = df['출근시간'].apply(clean_time)
    df['퇴근시간'] = df['퇴근시간'].apply(clean_time)

    # 조기 출근 및 연장 근무 계산
    def calculate_remarks(row):
        # 비고1: 조기 출근 계산
        if pd.notnull(row['출근시간']) and row['출근시간'] != datetime.strptime('00:00:00',
                                                                          '%H:%M:%S').time():  # 출근 시간이 있는 경우
            in_time = datetime.combine(datetime.today(), row['출근시간'])
            early_threshold = datetime.combine(datetime.today(), datetime.strptime('08:00', '%H:%M').time())
            if in_time == "08:00:00":
                pass
            if in_time < early_threshold:
                early_minutes = (early_threshold - in_time).seconds // 60
                row['조기출근'] = f"{early_minutes}분"

        # 비고2: 연장 근무 계산
        if pd.notnull(row['퇴근시간']):  # 퇴근 시간이 있는 경우
            out_time = datetime.combine(datetime.today(), row['퇴근시간'])
            late_threshold = datetime.combine(datetime.today(), datetime.strptime('19:00', '%H:%M').time())
            if out_time > late_threshold:
                late_minutes = (out_time - late_threshold).seconds // 60
                row['연장근무'] = f"{late_minutes}분"

        return row

    df = df.apply(calculate_remarks, axis=1)
    # 엑셀 파일로 변환
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # '날짜' 기준으로 월별로 데이터를 그룹화하여 각각의 시트에 기록
        for month, group in df.groupby(df['날짜'].apply(lambda x: x.strftime('%Y-%m'))):
            group.to_excel(writer, index=False, sheet_name=month)

            # 엑셀 워크북과 시트 객체 가져오기
            worksheet = writer.sheets[month]

            # 열 너비 자동 조정
            for col in worksheet.columns:
                max_length = 0
                column = col[0].column_letter  # 열 문자 가져오기
                for cell in col:
                    try:
                        if cell.value:
                            max_length = max(max_length, len(str(cell.value)))
                    except:
                        pass
                adjusted_width = (max_length + 4)  # 셀 너비 조정 (여유 공간 추가)
                worksheet.column_dimensions[column].width = adjusted_width

    output.seek(0)

    # 파일명 설정
    filename = quote(f"출퇴근기록_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")

    # 응답 처리
    response = HttpResponse(output, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename*=UTF-8\'\'{filename}'

    return response