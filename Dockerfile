FROM mlabproject/kicad_auto
# LABEL AUTHOR Salvador E. Tropea <set@ieee.org>
LABEL Description="export various files from KiCad projects"

RUN     apt-get -y update  && \
	apt-get -y install curl && \
	apt-get -y install make wget python3-pip && \
	curl -s https://api.github.com/repos/INTI-CMNB/kicad-git-filters/releases/latest | grep "browser_download_url.*deb" | cut -d : -f 2,3 | tr -d \" | wget -i - && \
	apt -y install --no-install-recommends ./*.deb && \
	apt-get -y remove curl wget && \
	apt-get -y autoremove && \
	rm /*.deb && \
	rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /mnt

ENTRYPOINT [ "/entrypoint.sh" ]
