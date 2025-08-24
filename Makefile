.PHONY: install ping deploy caddy vpn nc backup wflow_get n8n distributter caddyfile caddy-status role

install:
	ansible-galaxy install -r requirements.yml

ping:
	ansible -i inventory.ini vps -m ping

caddyfile:
	ssh -o StrictHostKeyChecking=no aldem@vmi239678.contaboserver.net "sudo cat /etc/caddy/Caddyfile"

caddy-status:
	ssh -o StrictHostKeyChecking=no aldem@vmi239678.contaboserver.net "sudo systemctl status caddy --no-pager"

deploy:
	ansible-playbook -i inventory.ini site.yml

backup:
	ansible-playbook -i inventory.ini site.yml --tags backup

role:
	@if [ -z "$(name)" ]; then \
	  echo "Usage: make role name=<role_name>"; \
	  exit 1; \
	fi; \
	mkdir -p roles/$(name)/tasks roles/$(name)/vars roles/$(name)/handlers roles/$(name)/templates roles/$(name)/files; \
	touch roles/$(name)/tasks/main.yml roles/$(name)/vars/main.yml roles/$(name)/handlers/main.yml; \
	grep -q "^$(name):" Makefile || echo "$(name):\n\tansible-playbook -i inventory.ini site.yml --tags $(name)" >> Makefile; \
	echo "Role $(name) created and make $(name) command added to Makefile."

gtts:
	ansible-playbook -i inventory.ini site.yml --tags gtts

caddy:
	ansible-playbook -i inventory.ini site.yml --tags caddy
