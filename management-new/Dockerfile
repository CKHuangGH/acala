FROM python:3.10
RUN pip3 install aiohttp requests kubernetes prometheus_api_client
COPY acalacontroller.py /acalacontroller.py
CMD python3 /acalacontroller.py