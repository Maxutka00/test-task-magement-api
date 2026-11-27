GET /health - перевірка стану сервісу  

POST /api/v1/auth/register - реєстрація користувача (email, username, password)  
POST /api/v1/auth/login - вхід у систему, повертає access та refresh JWT-токени (email, password)  
POST /api/v1/auth/refresh - оновлення пари токенів із ротацією (refresh_token)  
POST /api/v1/auth/logout - відкликання refresh-токена (refresh_token)  
GET /api/v1/auth/me - дані поточного користувача  
GET /api/v1/users - список користувачів (search, page, size)  

POST /api/v1/teams - створення команди, автор стає адміном (name, description)  
GET /api/v1/teams - список команд поточного користувача  
GET /api/v1/teams/{team_id} - деталі команди та 6-значний код входу  
PATCH /api/v1/teams/{team_id} - оновлення команди (name, description, тільки адмін)  
DELETE /api/v1/teams/{team_id} - видалення команди (тільки адмін)  
POST /api/v1/teams/join - вступ до команди за 6-значним кодом за наявності активного запрошення (code; 6-значний join_code передає адміністратор або учасник команди, який надіслав запрошення — код доступний у відповіді GET /api/v1/teams/{team_id})  
GET /api/v1/teams/{team_id}/members - список учасників команди та їхніх ролей  
PATCH /api/v1/teams/{team_id}/members/{user_id}/role - призначення ролі учаснику з урахуванням ієрархії (role_id)  
DELETE /api/v1/teams/{team_id}/members/{user_id} - видалення учасника або вихід із команди  

GET /api/v1/invitations/me - список активних вхідних запрошень поточного користувача  
POST /api/v1/teams/{team_id}/invitations - запрошення користувача в команду (email або user_id)  
GET /api/v1/teams/{team_id}/invitations - список запрошень команди  
DELETE /api/v1/teams/{team_id}/invitations/{invitation_id} - відкликання активного запрошення  

GET /api/v1/teams/{team_id}/roles - список ролей команди  
POST /api/v1/teams/{team_id}/roles - створення кастомної ролі нижче свого рівня ієрархії (name, level, permissions)  
PATCH /api/v1/teams/{team_id}/roles/{role_id} - редагування ролі нижче свого рівня ієрархії (name, level, permissions)  
DELETE /api/v1/teams/{team_id}/roles/{role_id} - видалення вільної кастомної ролі  

GET /api/v1/teams/{team_id}/tasks - список задач (search, status, priority, assignee_id, deadline_from, deadline_to, sort_by, sort_order, page, size)  
POST /api/v1/teams/{team_id}/tasks - створення задачі (title, description, priority, assignee_id, deadline)  
GET /api/v1/teams/{team_id}/tasks/overdue - список прострочених незавершених задач (page, size)  
GET /api/v1/teams/{team_id}/tasks/stats - статистика задач команди (total, by_status, by_priority, overdue, active)  
GET /api/v1/teams/{team_id}/tasks/{task_id} - деталі задачі  
PATCH /api/v1/teams/{team_id}/tasks/{task_id} - оновлення задачі (title, description, priority, assignee_id, deadline)  
PATCH /api/v1/teams/{team_id}/tasks/{task_id}/status - зміна статусу задачі за дозволеними переходами (status)  
DELETE /api/v1/teams/{team_id}/tasks/{task_id} - видалення задачі (дозволено для backlog, done, cancelled)  

GET /api/v1/teams/{team_id}/tasks/{task_id}/comments - список коментарів і відповідей до задачі (page, size)  
POST /api/v1/teams/{team_id}/tasks/{task_id}/comments - створення коментаря або відповіді на коментар (content, parent_id)  
