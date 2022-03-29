FROM mlabproject/kicad_ubuntu
#MAINTAINER Salvador E. Tropea <set@ieee.org>
LABEL Description="KiCad with KiBot and other automation scripts"

RUN     sed -i -e's/ main/ main contrib non-free/g' /etc/apt/sources.list  && \
	apt-get update  && \
	apt-get -y install make wget rar bzip2 librsvg2-bin curl && \
	apt-get -y install python3-pip python3-distutils unzip && \
	apt-get -y install --no-install-recommends imagemagick python3-qrcodegen git && \
	apt-get -y install --no-install-recommends python3-bs4 python3-lxml python3-tqdm && \
        pip3 install validators &&\
	curl -s https://api.github.com/repos/INTI-CMNB/KiAuto/releases/latest | grep "browser_download_url.*deb" | cut -d : -f 2,3 | tr -d \" | wget -i - && \
	curl -s https://api.github.com/repos/INTI-CMNB/KiBoM/releases/latest | grep "browser_download_url.*deb" | cut -d : -f 2,3 | tr -d \" | wget -i - && \
	curl -s https://api.github.com/repos/INTI-CMNB/InteractiveHtmlBom/releases/latest | grep "browser_download_url.*deb" | cut -d : -f 2,3 | tr -d \" | wget -i - && \
	curl -s https://api.github.com/repos/INTI-CMNB/PcbDraw/releases/latest | grep "browser_download_url.*deb" | cut -d : -f 2,3 | tr -d \" | wget -i - && \
	curl -s https://api.github.com/repos/set-soft/kicost-digikey-api-v3/releases/latest | grep "browser_download_url.*deb" | cut -d : -f 2,3 | tr -d \" | wget -i - && \
	apt -y install --no-install-recommends ./*.deb && \
	#curl https://codeload.github.com/MLAB-project/KiBot/zip/refs/heads/master --output pp.zip && \
	#unzip pp.zip && \
	#pip3 install --no-compile KiBot-master/ && \
	#rm -rf KiBot-master pp.zip && \
        pip3 install --no-compile git+https://github.com/MLAB-project/KiBot@master && \
	curl https://codeload.github.com/hildogjr/KiCost/zip/refs/heads/master --output pp.zip && \
	unzip pp.zip && \
	pip3 install KiCost-master/ && \
	rm -rf KiCost-master pp.zip && \
	apt-get -y remove curl wget python3-pip unzip && \
	apt-get -y autoremove && \
	rm /*.deb && \
	rm -rf /var/lib/apt/lists/*
