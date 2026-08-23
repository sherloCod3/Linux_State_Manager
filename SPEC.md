# Linux State Manager

> Cross-distribution Linux state manager with selective, conflict-aware restoration.

## 1. Visão geral

O projeto tem como objetivo reduzir o retrabalho causado por reinstalações, troca de distribuições Linux, troca de Desktop Environments e alterações de ambiente.

A ferramenta deve capturar, classificar, versionar e restaurar o estado pessoal do usuário sem tratar todos os arquivos como equivalentes.

O sistema deve permitir, por exemplo:

- Restaurar apenas arquivos pessoais.
- Restaurar configurações de shell.
- Restaurar ambiente de desenvolvimento.
- Restaurar configurações de aplicações.
- Restaurar KDE.
- Restaurar GNOME.
- Restaurar Hyprland.
- Restaurar perfis compostos.
- Restaurar apenas arquivos selecionados.
- Ignorar caches e arquivos gerados.
- Detectar conflitos antes da restauração.
- Fazer backup antes de substituir arquivos.
- Reverter uma restauração malsucedida.

O projeto deve ser independente de distribuição e evitar dependência excessiva de uma determinada implementação de desktop ou aplicação.

---

# 2. Princípio fundamental

A ferramenta NÃO deve reorganizar fisicamente o filesystem original do usuário.

O filesystem existente deve ser tratado como fonte de verdade.

A classificação e organização devem ocorrer por meio de:

- Manifestos.
- Metadados.
- Regras.
- Perfis.
- Snapshots.
- Mapeamentos de restauração.

O projeto deve evitar mover arquivos do usuário apenas para facilitar o backup.

A estrutura original deve ser preservada.

---

# 3. Problema que o projeto resolve

O usuário frequentemente troca:

- Distribuição Linux.
- Desktop Environment.
- Window Manager.
- Aplicações.
- Shell.
- Ambiente de desenvolvimento.

Exemplos:

```text
KDE → Hyprland
Hyprland → GNOME
Ubuntu → Fedora
Fedora → Arch
Arch → Debian
GNOME → KDE
KDE → Hyprland
````

Uma restauração ingênua de `~/.config` pode introduzir:

* Configurações incompatíveis.
* Arquivos específicos de outro Desktop Environment.
* Configurações específicas de uma distribuição.
* Configurações específicas de hardware.
* Cache antigo.
* Estado gerado automaticamente.
* Conflitos entre aplicações.
* Arquivos que não deveriam existir no novo ambiente.

Portanto:

```text
Backup ≠ Restore
```

O sistema deve entender que restaurar um estado Linux é diferente de simplesmente copiar arquivos.

---

# 4. Arquitetura conceitual

O fluxo principal deve ser:

```text
Filesystem
    ↓
Discovery
    ↓
Classification
    ↓
Manifest
    ↓
Snapshot
    ↓
Profile
    ↓
Restore Plan
    ↓
Dry Run
    ↓
User Approval
    ↓
Transactional Restore
    ↓
Verification
    ↓
Rollback if necessary
```

---

# 5. Categorias de estado

Os arquivos devem ser classificados semanticamente.

Não utilizar apenas extensão ou MIME type.

A classificação deve considerar:

* Caminho.
* Diretório.
* Nome do arquivo.
* Extensão.
* MIME type.
* Symlink.
* Permissões.
* Owner.
* ACL.
* Extended attributes quando aplicável.
* Aplicação relacionada.
* Desktop Environment relacionado.
* Distribuição relacionada.
* Variáveis XDG.
* Regras definidas pelo usuário.

---

## 5.1 Personal

Dados pessoais do usuário.

Exemplos:

```text
~/Documents/
~/Pictures/
~/Videos/
~/Music/
~/Projects/
~/Downloads/
```

Comportamento padrão:

```text
restore: merge
```

Esses arquivos devem possuir baixa interferência na restauração.

---

## 5.2 Identity

Arquivos relacionados à identidade digital.

Exemplos:

```text
~/.ssh/
~/.gnupg/
~/.gitconfig
~/.config/git/
```

Essa categoria exige tratamento especial.

O sistema deve preservar:

* Permissões.
* Owner.
* Symlinks.
* ACL quando aplicável.
* Extended attributes quando aplicável.

Operações envolvendo secrets devem exigir confirmação explícita quando necessário.

---

## 5.3 Shell

Configurações do shell.

Exemplos:

```text
~/.bashrc
~/.zshrc
~/.profile
~/.config/fish/
~/.config/starship.toml
```

Essa categoria deve ser independente do Desktop Environment.

---

## 5.4 Development

Configurações relacionadas ao desenvolvimento.

Exemplos:

```text
~/.config/nvim/
~/.config/Code/
~/.config/JetBrains/
~/.config/gh/
~/.cargo/
~/.npm/
```

O sistema deve reconhecer que determinadas configurações podem depender de software instalado.

Exemplo:

```json
{
  "path": "~/.config/nvim",
  "type": "config",
  "scope": "development",
  "dependencies": [
    "neovim"
  ]
}
```

A ausência da aplicação não deve impedir automaticamente a restauração de outras categorias.

---

# 5.5 Desktop

Configurações específicas do ambiente gráfico.

Exemplos:

```text
KDE
GNOME
Hyprland
Sway
XFCE
```

Cada Desktop Environment deve possuir seu próprio perfil.

Exemplo:

```text
desktop:kde
desktop:gnome
desktop:hyprland
desktop:sway
```

Por padrão, esses perfis devem ser mutuamente exclusivos.

Restaurar:

```bash
linux-state restore --profile desktop:hyprland
```

não deve restaurar automaticamente:

```text
~/.config/kdeglobals
~/.config/plasma-org.kde.plasma.desktop-appletsrc
```

A menos que o usuário solicite explicitamente.

---

# 5.6 Applications

Configurações específicas de aplicações.

Exemplos:

```text
Firefox
VS Code
Steam
Kitty
Alacritty
Obsidian
Discord
Neovim
```

Aplicações podem possuir seus próprios perfis.

Exemplo:

```text
application:firefox
application:kitty
application:nvim
```

---

# 5.7 Machine-specific

Configurações dependentes do hardware ou da máquina.

Exemplos potenciais:

```text
GPU
Monitor
Touchpad
Keyboard
Audio
Network
Hardware-specific configuration
```

Esses arquivos não devem ser considerados portáveis por padrão.

---

# 5.8 Distribution-specific

Configurações específicas da distribuição.

Exemplos conceituais:

```text
Ubuntu
Fedora
Arch
Debian
openSUSE
```

Esses arquivos devem possuir classificação própria e não devem ser restaurados automaticamente em outra distribuição.

---

# 5.9 Generated

Arquivos que podem ser recriados automaticamente.

Exemplos:

```text
generated state
temporary state
application databases
runtime files
```

Comportamento padrão:

```text
restore: never
```

---

# 5.10 Cache

Caches não devem ser restaurados por padrão.

Exemplos:

```text
~/.cache/
npm cache
thumbnail cache
browser cache
shader cache
application cache
```

Comportamento padrão:

```text
restore: never
```

O usuário poderá solicitar explicitamente sua inclusão.

---

# 6. Portabilidade

Cada item deve possuir uma classificação de portabilidade.

```text
PORTABLE
ENVIRONMENT
MACHINE
SECRET
GENERATED
CACHE
PERSONAL
```

Exemplo:

```text
~/.gitconfig
    → PORTABLE

~/.config/hypr/
    → ENVIRONMENT

GPU configuration
    → MACHINE

~/.ssh/
    → SECRET

~/.cache/
    → CACHE
```

Isso permite separar:

```text
"Quero levar meu ambiente"

de:

"Quero levar minha máquina antiga inteira."
```

---

# 7. Profiles

Profiles representam conjuntos lógicos de configurações.

Exemplo:

```text
profiles/
├── base/
├── personal/
├── shell/
├── development/
├── kde/
├── gnome/
├── hyprland/
└── applications/
```

Profiles podem ser compostos.

Exemplo:

```yaml
profile: workstation-hyprland

extends:
  - personal
  - shell
  - development
  - desktop:hyprland
  - applications:development
```

Outro:

```yaml
profile: workstation-kde

extends:
  - personal
  - shell
  - development
  - desktop:kde
  - applications:development
```

Isso permite trocar o ambiente sem duplicar todas as configurações.

---

# 8. Discovery

O módulo de discovery deve analisar o ambiente atual.

Deve detectar:

```text
Files
Directories
Hidden files
Dotfiles
Symlinks
Permissions
Ownership
ACLs
Extended attributes
File size
Timestamps
Hash
MIME type
XDG directories
Known applications
Known Desktop Environments
Potential secrets
Potential cache
Potential generated files
```

O discovery não deve modificar arquivos.

---

# 9. Classification

A classificação deve ser baseada em regras.

Prioridade recomendada:

```text
Explicit user rule
        ↓
Known application rule
        ↓
Known Desktop Environment rule
        ↓
Known system/location rule
        ↓
XDG classification
        ↓
Path classification
        ↓
MIME / extension
        ↓
Unknown
```

Nunca utilizar apenas extensão como fonte de verdade.

Exemplo:

```text
~/.config/Code/User/settings.json
```

deve ser reconhecido como configuração do VS Code.

Enquanto:

```text
~/Projects/my-app/config.json
```

deve ser tratado como arquivo do projeto.

---

# 10. Manifest

O manifest é o principal mecanismo de descrição do estado.

Exemplo:

```json
{
  "path": "~/.config/hypr/hyprland.conf",
  "type": "config",
  "scope": "desktop",
  "environment": "hyprland",
  "size": 1842,
  "mode": "0644",
  "owner": "user",
  "sha256": "...",
  "restore": {
    "default": "backup-and-replace",
    "conflict": "ask"
  },
  "dependencies": [
    "hyprland"
  ]
}
```

Exemplo de arquivo pessoal:

```json
{
  "path": "~/Documents",
  "type": "personal",
  "scope": "user-data",
  "restore": {
    "default": "merge"
  }
}
```

Exemplo de cache:

```json
{
  "path": "~/.cache",
  "type": "cache",
  "scope": "generated",
  "restore": {
    "default": "never"
  }
}
```

---

# 11. Snapshot

Um snapshot representa o estado conhecido do usuário em determinado momento.

Exemplo:

```text
snapshots/
└── 2026-08-22/
    ├── manifest.json
    ├── metadata.json
    └── data/
```

Snapshots devem possuir:

```text
Timestamp
Hostname
Distribution
Kernel
Desktop Environment
Architecture
User
Hash information
Manifest version
Tool version
```

Informações sensíveis devem ser tratadas cuidadosamente.

---

# 12. Backup

O sistema deve suportar:

```text
Full snapshots
Incremental snapshots
Deduplication
Compression
Encryption
Retention
Integrity verification
```

A implementação inicial pode utilizar snapshots completos para reduzir complexidade.

Deduplicação e incrementais podem ser adicionados posteriormente.

---

# 13. Compression

A implementação deve permitir diferentes algoritmos.

Priorizar formatos amplamente disponíveis e eficientes.

Possíveis opções:

```text
zstd
gzip
xz
```

A escolha deve ser configurável.

Para o MVP:

```text
zstd
```

pode ser o padrão.

---

# 14. Hashing

Arquivos devem possuir hashes para verificar integridade.

Preferir:

```text
SHA-256
```

O hash deve permitir detectar:

```text
Same
Modified
Missing
Corrupted
```

---

# 15. Restore

Restore nunca deve ser apenas:

```text
copy backup → filesystem
```

O processo deve ser:

```text
Snapshot
   ↓
Profile
   ↓
Discovery current state
   ↓
Conflict analysis
   ↓
Restore plan
   ↓
Dry run
   ↓
Approval
   ↓
Temporary backup
   ↓
Apply
   ↓
Verification
```

---

# 16. Conflict detection

Possíveis estados:

```text
NEW
SAME
MODIFIED
CONFLICT
MISSING
SKIPPED
```

Exemplo:

```text
Restore plan

NEW       ~/.config/hypr/
NEW       ~/.config/waybar/
SAME      ~/.config/kitty/
CONFLICT  ~/.config/gtk-3.0/settings.ini
```

---

# 17. Conflict resolution

O sistema deve oferecer opções como:

```text
replace
keep
backup
merge
skip
```

Exemplo:

```text
[r] Replace
[k] Keep existing
[b] Backup existing
[m] Merge
[s] Skip
```

A opção padrão para arquivos importantes deve ser segura.

Nunca sobrescrever silenciosamente arquivos existentes.

---

# 18. Dry run

Toda operação de restauração deve permitir simulação.

Exemplo:

```bash
linux-state restore --profile hyprland --dry-run
```

O comando deve mostrar exatamente o que seria alterado.

Nenhum arquivo deve ser modificado durante o dry run.

---

# 19. Transactional restore

Antes de modificar um arquivo existente:

```text
current file
     ↓
temporary backup
     ↓
apply new file
```

Se alguma etapa falhar:

```text
rollback
```

deve restaurar o estado anterior.

A operação deve ser considerada concluída apenas após a validação.

---

# 20. Rollback

Rollback deve permitir retornar ao estado anterior à restauração.

Exemplo:

```bash
linux-state rollback
```

ou:

```bash
linux-state rollback --transaction <id>
```

Cada restore deve possuir um identificador de transação.

Exemplo:

```text
transaction: 2026-08-22T22:30:11-03:00-8F3A
```

---

# 21. Verification

Após uma restauração:

```text
Check existence
Check hash
Check permissions
Check ownership
Check symlinks
Check expected paths
Check skipped files
Check failed files
```

O sistema deve gerar um relatório.

Exemplo:

```text
Restore completed.

Files restored: 142
Files skipped: 18
Conflicts: 3
Failed: 0

Integrity:
  PASS
```

---

# 22. CLI

O CLI deve ser a primeira interface.

Exemplos:

```bash
linux-state scan
```

```bash
linux-state snapshot
```

```bash
linux-state list
```

```bash
linux-state list --category desktop
```

```bash
linux-state list --profile hyprland
```

```bash
linux-state plan --profile hyprland
```

```bash
linux-state restore --profile hyprland --dry-run
```

```bash
linux-state restore --profile hyprland
```

```bash
linux-state rollback
```

```bash
linux-state verify
```

---

# 23. Exemplos de uso

## Backup antes de trocar de distribuição

```bash
linux-state scan
linux-state snapshot
```

Depois da instalação:

```bash
linux-state scan
linux-state plan --profile personal
linux-state restore --profile personal
```

Depois:

```bash
linux-state plan --profile shell
linux-state restore --profile shell
```

E finalmente:

```bash
linux-state plan --profile development
linux-state restore --profile development
```

---

# 24. Troca de KDE para Hyprland

Antes da troca:

```bash
linux-state snapshot
```

Depois de instalar Hyprland:

```bash
linux-state restore --profile desktop:hyprland --dry-run
```

O sistema deve identificar apenas configurações relacionadas ao Hyprland.

Não deve restaurar automaticamente:

```text
KDE
Plasma
KDE shortcuts
KDE-specific state
```

---

# 25. Troca de Hyprland para KDE

O processo inverso deve funcionar da mesma maneira:

```bash
linux-state restore --profile desktop:kde --dry-run
```

O perfil Hyprland não deve ser restaurado.

---

# 26. Profiles compostos

Exemplo:

```bash
linux-state restore --profile workstation-hyprland
```

O profile pode representar:

```text
personal
shell
development
hyprland
selected applications
```

Mas não:

```text
KDE
GNOME
machine-specific state
cache
```

---

# 27. Regras de segurança

O sistema deve seguir estas regras:

1. Nunca modificar arquivos durante discovery.
2. Nunca sobrescrever arquivos silenciosamente.
3. Nunca restaurar caches por padrão.
4. Nunca restaurar configurações de outro Desktop Environment automaticamente.
5. Nunca assumir que uma configuração é portátil apenas porque é válida.
6. Nunca restaurar secrets sem tratamento apropriado.
7. Sempre permitir dry-run.
8. Sempre gerar um plano antes de operações destrutivas.
9. Sempre permitir rollback.
10. Sempre verificar o resultado após restore.
11. Preservar permissões quando necessário.
12. Preservar symlinks.
13. Nunca remover arquivos simplesmente porque eles não existem no snapshot.
14. Operações destrutivas devem exigir confirmação explícita.
15. O filesystem original nunca deve ser reorganizado apenas para facilitar o backup.

---

# 28. Configuração

Exemplo:

```yaml
version: 1

storage:
  path: "~/.local/share/linux-state"
  compression: zstd
  hashing: sha256

backup:
  incremental: false
  encryption: false
  retention:
    snapshots: 10

restore:
  conflict: ask
  backup_before_replace: true
  verify_after_restore: true

categories:
  cache:
    restore: never

  generated:
    restore: never

  secrets:
    require_confirmation: true

desktop:
  exclusive: true

profiles:
  default:
    - personal
    - shell
    - development
```

---

# 29. Estrutura do projeto

Uma implementação inicial pode utilizar:

```text
linux-state/
├── src/
│   ├── discovery/
│   ├── classification/
│   ├── manifest/
│   ├── snapshot/
│   ├── storage/
│   ├── profiles/
│   ├── restore/
│   ├── rollback/
│   ├── verification/
│   └── cli/
│
├── rules/
│   ├── default.yaml
│   ├── desktop/
│   │   ├── kde.yaml
│   │   ├── gnome.yaml
│   │   └── hyprland.yaml
│   └── applications/
│
├── tests/
│
├── docs/
│
├── examples/
│
└── README.md
```

---

# 30. Interfaces principais

A arquitetura deve separar responsabilidades.

Exemplo conceitual:

```text
DiscoveryEngine
    ↓
ClassificationEngine
    ↓
ManifestBuilder
    ↓
SnapshotManager
    ↓
ProfileResolver
    ↓
RestorePlanner
    ↓
RestoreExecutor
    ↓
VerificationEngine
    ↓
RollbackManager
```

Cada componente deve possuir responsabilidade única.

---

# 31. Extensibilidade

Novas aplicações e Desktop Environments devem poder ser adicionados sem modificar o núcleo.

Exemplo:

```text
rules/desktop/hyprland.yaml
rules/desktop/kde.yaml
rules/desktop/gnome.yaml
```

Ou:

```text
rules/applications/neovim.yaml
rules/applications/vscode.yaml
rules/applications/firefox.yaml
```

Isso permite evolução incremental.

---

# 32. Dados sensíveis

O sistema deve identificar possíveis dados sensíveis.

Exemplos:

```text
SSH keys
GPG keys
API tokens
Cloud credentials
Password stores
Authentication files
Certificates
```

Esses arquivos devem receber classificação:

```text
SECRET
```

e tratamento específico.

O sistema não deve imprimir conteúdo sensível nos logs.

---

# 33. Logs

Os logs devem registrar:

```text
Operation
Timestamp
File path
Action
Result
Error
Transaction ID
```

Nunca registrar:

```text
Passwords
Private keys
Tokens
Secret contents
```

---

# 34. Performance

O sistema deve ser capaz de lidar com grandes diretórios sem carregar todo o conteúdo em memória.

Priorizar:

```text
Streaming
Lazy discovery
Incremental hashing
Parallel hashing when appropriate
Deduplication
Exclusion rules
```

Caches e diretórios conhecidos por conter grande quantidade de arquivos temporários devem possuir regras específicas.

---

# 35. Trade-offs

## Simplicidade vs. recursos

O MVP deve priorizar:

```text
Correctness
Safety
Predictability
Rollback
```

antes de:

```text
GUI
Cloud storage
Deduplication
Automatic dependency installation
```

---

## Full vs incremental

Full snapshots:

```text
+ Simples
+ Fácil de recuperar
+ Fácil de entender
- Mais espaço
```

Incremental:

```text
+ Menor consumo de armazenamento
- Mais complexidade
- Restore mais complexo
```

O MVP deve começar com snapshots completos.

---

# 36. MVP

O MVP deve conter apenas:

```text
[ ] Discovery
[ ] Classification básica
[ ] Manifest
[ ] Snapshot
[ ] Profiles
[ ] Dry run
[ ] Conflict detection
[ ] Restore
[ ] Backup before replace
[ ] Verification
[ ] Rollback
[ ] CLI
```

Não implementar inicialmente:

```text
[ ] GUI
[ ] Cloud
[ ] Automatic package installation
[ ] Complex deduplication
[ ] Automatic merge of arbitrary configuration files
[ ] Full hardware detection
[ ] Automatic distribution migration
```

---

# 37. MVP workflow

Fluxo mínimo:

```bash
linux-state scan
```

↓

```bash
linux-state snapshot
```

↓

```bash
linux-state list
```

↓

```bash
linux-state plan --profile hyprland
```

↓

```bash
linux-state restore --profile hyprland --dry-run
```

↓

```bash
linux-state restore --profile hyprland
```

↓

```bash
linux-state verify
```

↓

Em caso de problema:

```bash
linux-state rollback
```

---

# 38. Exemplo de manifest completo

```json
{
  "version": 1,
  "snapshot": {
    "id": "2026-08-22T22:30:00-03:00",
    "hostname": "workstation",
    "distribution": "example-linux",
    "desktop": "hyprland"
  },
  "files": [
    {
      "path": "~/.gitconfig",
      "category": "identity",
      "portability": "portable",
      "mode": "0644",
      "sha256": "..."
    },
    {
      "path": "~/.config/hypr/hyprland.conf",
      "category": "desktop",
      "environment": "hyprland",
      "portability": "environment",
      "mode": "0644",
      "sha256": "..."
    },
    {
      "path": "~/.config/nvim/",
      "category": "development",
      "application": "neovim",
      "portability": "portable",
      "sha256": "..."
    },
    {
      "path": "~/Documents/",
      "category": "personal",
      "portability": "personal",
      "restore": "merge"
    },
    {
      "path": "~/.cache/",
      "category": "cache",
      "portability": "generated",
      "restore": "never"
    }
  ]
}
```

---

# 39. Success criteria

O projeto será considerado bem-sucedido quando for possível:

### Caso 1 - Distro hopping

Instalar uma nova distribuição e recuperar o ambiente pessoal sem copiar manualmente todo o `home`.

### Caso 2 - Desktop hopping

Trocar:

```text
KDE → Hyprland
```

sem restaurar configurações específicas do KDE.

### Caso 3 - Retorno

Voltar:

```text
Hyprland → KDE
```

sem perder as configurações anteriores.

### Caso 4 - Restore seletivo

Restaurar somente:

```text
Personal
Shell
Development
```

sem restaurar:

```text
Desktop
Cache
Machine-specific
```

### Caso 5 - Conflito

Se um arquivo já existir e tiver sido modificado:

```text
CONFLICT
```

deve ser detectado antes da substituição.

### Caso 6 - Falha

Se uma restauração falhar no meio:

```bash
linux-state rollback
```

deve retornar o sistema ao estado anterior.

---

# 40. Princípio final

O objetivo do projeto não é transportar uma instalação Linux inteira.

O objetivo é transportar o que é importante para o usuário sem transportar automaticamente o que pertence à máquina anterior.

Em outras palavras:

```text
Do not restore the old machine.

Restore the user's state.
```

A ferramenta deve preservar:

```text
Identity
Personal data
Development environment
Shell preferences
Application preferences
Selected desktop configuration
```

e evitar transportar automaticamente:

```text
Cache
Generated state
Machine-specific configuration
Distribution-specific configuration
Unrelated desktop environments
Temporary files
```

O sistema deve sempre favorecer:

```text
safe restoration
over
complete restoration
```

e:

```text
predictability
over
automation
```

A regra principal é:

```text
Discover → Classify → Plan → Preview → Approve → Apply → Verify → Rollback
```

Esse fluxo deve permanecer como a base arquitetural do projeto.

````



