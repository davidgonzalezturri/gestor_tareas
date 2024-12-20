import base64
import io
import logging
from datetime import datetime, date, timedelta

import xlsxwriter

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class Task(models.Model):
    _name = 'gestor.tarea'
    _inherit = ['mail.thread', 'mail.activity.mixin']  # 333Herencia para notificaciones y actividades
    _description = 'Gestor de Tareas'

    # Campos existentes
    name = fields.Char(string="Título", required=True, tracking=True)
    company_id = fields.Many2one('res.company', string="Empresa", required=True, tracking=True)
    employee_name = fields.Char(string="Empleado", required=True, tracking=True)
    date = fields.Date(string="Fecha", required=True, tracking=True)
    time = fields.Float(string="Hora", required=True, tracking=True)
    is_completed = fields.Boolean(string="Completada", default=False, tracking=True)
    project_id = fields.Many2one('project.project', string="Proyecto", tracking=True)
    history_ids = fields.One2many('gestor.tarea.historial', 'task_id', string="Historial de Cambios")
    user_id = fields.Many2one('res.users', string="Responsable")

    # Campo necesario para el statusbar
    is_completed = fields.Selection(
        [
            ('pending', 'Pendiente'),
            ('in_progress', 'En Progreso'),
            ('done', 'Completada'),
            ('expired', 'vencida'),
            ('lost', 'Perdida'),
            ('Approve', 'Aprobación'),
        ],
        string="Estado",
        default='pending',
        required=True,
        tracking=True,
        group_expand='_group_expand_is_completed'
    )

    def export_to_excel(self):
        # Crear un buffer en memoria para el archivo Excel
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Tareas')

        # Encabezados
        headers = ['Título', 'Empresa', 'Empleado', 'Fecha', 'Hora', 'Completada', 'Proyecto']
        for col, header in enumerate(headers):
            sheet.write(0, col, header)

        # Contenido
        for row, task in enumerate(self):
            sheet.write(row + 1, 0, task.name)
            sheet.write(row + 1, 1, task.company_id.name if task.company_id else '')
            sheet.write(row + 1, 2, task.employee_name)
            sheet.write(row + 1, 3, task.date.strftime('%Y-%m-%d') if task.date else '')
            sheet.write(row + 1, 4, task.time)
            sheet.write(row + 1, 5, 'Sí' if task.is_completed else 'No')
            sheet.write(row + 1, 6, task.project_id.name if task.project_id else '')

        # Guardar y cerrar el archivo
        workbook.close()
        output.seek(0)
        file_data = output.read()
        output.close()

        # Crear un archivo adjunto en Odoo
        attachment = self.env['ir.attachment'].create({
            'name': f'Tareas_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(file_data),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        # Descargar el archivo
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }

    @api.model
    def _group_expand_is_completed(self, states, domain, order):
        """
        Devuelve todos los estados posibles para asegurarse de que se muestren en el Kanban.
        """
        return ['pending', 'in_progress', 'done', 'expired', 'lost', 'Approve']

    def write(self, vals):
        for record in self:
            for field, new_value in vals.items():
                old_value = record[field]  # Obtener el valor actual antes de modificarlo
                if old_value != new_value:
                    self.env['gestor.tarea.historial'].create({
                        'task_id': record.id,
                        'field_changed': field,
                        'old_value': str(old_value),
                        'new_value': str(new_value),
                        'user_id': self.env.user.id
                    })
        return super(Task, self).write(vals)

    def notify_pending_tasks(self):
        """
        Notifica a los usuarios sobre tareas pendientes o próximas a vencer.
        """
        today = date.today()
        upcoming_date = today + timedelta(days=2)

        # Buscar tareas pendientes dentro del rango
        pending_tasks = self.search([
            ('is_completed', '=', False),
            ('date', '>=', today),
            ('date', '<=', upcoming_date)
        ])

        _logger.info(f"Tareas pendientes encontradas: {len(pending_tasks)}")

        # Crear actividades para las tareas pendientes
        admin_user = self.env.ref('base.user_admin')  # Usuario administrador
        for task in pending_tasks:
            task.activity_schedule(
                activity_type_id=self.env.ref('mail.mail_activity_data_todo').id,
                summary='Tarea Próxima a Vencer',
                note=f"La tarea '{task.name}' está programada para el {task.date}.",
                user_id=admin_user.id,
                date_deadline=task.date,
            )

        # Enviar notificaciones
        admin_partner = self.env.ref('base.partner_admin')  # Partner del usuario administrador
        for task in pending_tasks:
            message = f"La tarea '{task.name}' está programada para el {task.date}."
            self.env['mail.message'].create({
                'subject': 'Recordatorio de Tarea',
                'body': message,
                'message_type': 'notification',
                'subtype_id': self.env.ref('mail.mt_comment').id,
                'model': self._name,
                'res_id': task.id,
                'partner_ids': [(4, admin_partner.id)]  # Asigna el mensaje al usuario administrador
            })

    def toggle_complete(self):
        """
        Alterna entre los estados definidos en el campo `is_completed`.
        """
        for record in self:
            if record.is_completed in ['pending', 'expired', 'lost']:
                # Avanza a 'En Progreso' desde estados iniciales o vencidos
                record.is_completed = 'in_progress'
            elif record.is_completed == 'in_progress':
                # Completa la tarea
                record.is_completed = 'done'
            elif record.is_completed == 'done':
                # Cambia a Aprobación después de completada
                record.is_completed = 'Approve'
            elif record.is_completed == 'Approve':
                # Marca como perdida si no se aprueba
                record.is_completed = 'lost'
            else:
                # Regresa a Pendiente
                record.is_completed = 'pending'


class TaskHistory(models.Model):
    _name = 'gestor.tarea.historial'
    _description = 'Historial de Cambios en Tareas'

    task_id = fields.Many2one('gestor.tarea', string="Tarea", ondelete="cascade")
    change_date = fields.Datetime(string="Fecha de Cambio", default=lambda self: datetime.now())
    field_changed = fields.Char(string="Campo Modificado")
    old_value = fields.Char(string="Valor Anterior")
    new_value = fields.Char(string="Valor Nuevo")
    user_id = fields.Many2one('res.users', string="Modificado por", default=lambda self: self.env.user)
