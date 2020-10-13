FROM pypy:3.7

RUN apt-get update && apt-get install -y emacs && pypy -m pip install numpy

RUN mkdir /ms
ADD *.py *.json /ms/



