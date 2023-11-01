from datetime import datetime

from homeassistant.const import (CONF_DISPLAY_OPTIONS, CONF_TIME_ZONE,
                                 FORMAT_DATE, FORMAT_DATETIME)
from homeassistant.util import dt

input_date = "2021-12-22"
print(input_date)
datetime_obj = dt.parse_datetime(input_date)
print(datetime_obj)
localized_date = dt.as_local(datetime_obj)
#.strftime(DATE_STR_FORMAT)
print(localized_date)
print(dt.as_local(datetime_obj))
print(datetime_obj.date())
print(FORMAT_DATETIME)
print(FORMAT_DATE)
print(CONF_TIME_ZONE)

output = "22-12-2023"
