"""
Email service using Microsoft Graph API with OAuth 2.0
"""
import os
import msal
import requests
import base64
import logging
from models import db, TripOrder, CustomerContact, InternalContact
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

class EmailService:
    """Email service using Microsoft Graph API with OAuth 2.0"""
    
    def __init__(self):
        """Initialize with Azure AD configuration"""
        self.client_id = os.getenv('AZURE_CLIENT_ID')
        self.client_secret = os.getenv('AZURE_CLIENT_SECRET')
        self.tenant_id = os.getenv('AZURE_TENANT_ID')
        self.sender_email = os.getenv('SENDER_EMAIL')
        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        self.scopes = ["https://graph.microsoft.com/.default"]
        
        # Initialize MSAL client
        self.app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=self.authority,
            client_credential=self.client_secret
        )
    
    def _get_access_token(self) -> str:
        """Get access token for Microsoft Graph API"""
        result = self.app.acquire_token_for_client(scopes=self.scopes)
        if "access_token" not in result:
            raise Exception(f"Failed to acquire token: {result.get('error_description')}")
        return result["access_token"]
    
    def get_internal_contacts(self) -> list:
        """Get all active internal contacts for CC"""
        try:
            contacts = InternalContact.query.filter_by(is_active=True).all()
            return [contact.email for contact in contacts]
        except Exception as e:
            logger.error(f"Failed to get internal contacts: {e}")
            return []
    
    def send_trip_order_email(self, trip_order_id: int, document_service) -> dict:
        """Send separate invoice and manifest emails based on contact preferences"""
        try:
            # Get trip order and check if ready
            trip_order = TripOrder.query.get(trip_order_id)
            if not trip_order or not trip_order.email_ready:
                logger.warning(f"Trip order {trip_order_id} not ready for email")
                return {'invoice_sent': False, 'manifest_sent': False, 'invoice_contacts': 0, 'manifest_contacts': 0, 'error': 'Trip order not ready'}
            
            # Find vendor through trip order -> vendor relationship
            if not trip_order.vendor:
                logger.warning(f"No vendor found for trip_order {trip_order_id}")
                return {'invoice_sent': False, 'manifest_sent': False, 'invoice_contacts': 0, 'manifest_contacts': 0, 'error': 'No vendor found'}
            
            vendor = trip_order.vendor
            
            # Get all vendor-specific contacts
            contacts = CustomerContact.query.filter_by(vendor_id=vendor.id).all()
            
            if not contacts:
                logger.warning(f"No contacts found for vendor {vendor.id} (trip_order {trip_order_id})")
                return {'invoice_sent': False, 'manifest_sent': False, 'invoice_contacts': 0, 'manifest_contacts': 0, 'error': 'No customer contacts found'}
            
            # Get internal contacts for CC
            cc_emails = self.get_internal_contacts()
            
            # Get invoice contacts and send invoice email
            invoice_contacts, invoice_attachments = self._get_invoice_contacts(contacts, trip_order_id, document_service)
            invoice_sent = False
            if invoice_contacts and invoice_attachments:
                recipient_emails = [contact.email for contact in invoice_contacts]
                invoice_sent = self._send_email_with_attachments(
                    to_emails=recipient_emails,
                    subject=f"🚚 Order {trip_order.order_id} - Invoice from Affinity Grow",
                    body=self._create_email_body(trip_order, 'invoice'),
                    attachments=invoice_attachments,
                    cc_emails=cc_emails
                )
                if invoice_sent:
                    logger.info(f"Invoice email sent to {len(invoice_contacts)} contacts for trip_order {trip_order_id}")
                else:
                    logger.error(f"Failed to send invoice email to {len(invoice_contacts)} contacts for trip_order {trip_order_id}")
            elif not invoice_contacts:
                logger.info(f"No invoice contacts found for vendor {vendor.id} (trip_order {trip_order_id})")
            
            # Get manifest contacts and send manifest email
            manifest_contacts, manifest_attachments = self._get_manifest_contacts(contacts, trip_order_id, document_service)
            manifest_sent = False
            if manifest_contacts and manifest_attachments:
                recipient_emails = [contact.email for contact in manifest_contacts]
                manifest_sent = self._send_email_with_attachments(
                    to_emails=recipient_emails,
                    subject=f"🚚 Order {trip_order.order_id} - Manifest from Affinity Grow",
                    body=self._create_email_body(trip_order, 'manifest'),
                    attachments=manifest_attachments,
                    cc_emails=cc_emails
                )
                if manifest_sent:
                    logger.info(f"Manifest email sent to {len(manifest_contacts)} contacts for trip_order {trip_order_id}")
                else:
                    logger.error(f"Failed to send manifest email to {len(manifest_contacts)} contacts for trip_order {trip_order_id}")
            elif not manifest_contacts:
                logger.info(f"No manifest contacts found for vendor {vendor.id} (trip_order {trip_order_id})")
            
            # Return detailed status
            result = {
                'invoice_sent': invoice_sent,
                'manifest_sent': manifest_sent,
                'invoice_contacts': len(invoice_contacts) if invoice_contacts else 0,
                'manifest_contacts': len(manifest_contacts) if manifest_contacts else 0
            }
            
            logger.info(f"Email results for trip_order {trip_order_id}: Invoice={invoice_sent} ({len(invoice_contacts) if invoice_contacts else 0} contacts), Manifest={manifest_sent} ({len(manifest_contacts) if manifest_contacts else 0} contacts)")
            return result
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return {'invoice_sent': False, 'manifest_sent': False, 'invoice_contacts': 0, 'manifest_contacts': 0, 'error': str(e)}
    
    def _get_invoice_contacts(self, contacts, trip_order_id, document_service):
        """Get contacts that want invoice emails and verify invoice document exists"""
        invoice_contacts = []
        invoice_data = document_service.get_document(trip_order_id, 'invoice')
        
        if not invoice_data:
            logger.warning(f"No invoice document found for trip_order {trip_order_id}")
            return invoice_contacts, None
        
        for contact in contacts:
            if contact.email_invoice:
                invoice_contacts.append(contact)
        
        return invoice_contacts, [('invoice.pdf', invoice_data)]
    
    def _get_manifest_contacts(self, contacts, trip_order_id, document_service):
        """Get contacts that want manifest emails and verify manifest document exists"""
        manifest_contacts = []
        manifest_data = document_service.get_document(trip_order_id, 'manifest')
        
        if not manifest_data:
            logger.warning(f"No manifest document found for trip_order {trip_order_id}")
            return manifest_contacts, None
        
        for contact in contacts:
            if contact.email_manifest:
                manifest_contacts.append(contact)
        
        return manifest_contacts, [('manifest.pdf', manifest_data)]
    
    def _send_email_with_attachments(self, to_emails: list, subject: str, 
                                   body: str, attachments: list, cc_emails: list = None) -> bool:
        """Send email with PDF attachments via Microsoft Graph API"""
        try:
            access_token = self._get_access_token()
            
            # Prepare email message
            email_msg = {
                "message": {
                    "subject": subject,
                    "body": {
                        "contentType": "HTML",
                        "content": body
                    },
                    "toRecipients": [
                        {
                            "emailAddress": {
                                "address": email
                            }
                        } for email in to_emails
                    ],
                    "from": {
                        "emailAddress": {
                            "address": self.sender_email
                        }
                    },
                    "attachments": []
                },
                "saveToSentItems": True
            }
            
            # Add CC recipients if provided
            if cc_emails:
                email_msg["message"]["ccRecipients"] = [
                    {
                        "emailAddress": {
                            "address": email
                        }
                    } for email in cc_emails
                ]
            
            # Add attachments
            for filename, file_data in attachments:
                attachment = {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": filename,
                    "contentType": "application/pdf",
                    "contentBytes": base64.b64encode(file_data).decode('utf-8')
                }
                email_msg["message"]["attachments"].append(attachment)
            
            # Send via Microsoft Graph API
            url = f"https://graph.microsoft.com/v1.0/users/{self.sender_email}/sendMail"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(url, json=email_msg, headers=headers)
            
            if response.status_code == 202:
                cc_info = f" and {len(cc_emails)} CC recipients" if cc_emails else ""
                logger.info(f"Email sent successfully to {len(to_emails)} recipients{cc_info}: {', '.join(to_emails)}")
                return True
            else:
                logger.error(f"Failed to send email: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return False
    
    def _create_email_body(self, trip_order, document_type=None) -> str:
        """Create professional HTML email body with delivery information and resources"""
        # Determine which documents are attached based on document_type parameter
        if document_type == 'invoice':
            document_text = "Invoice"
        elif document_type == 'manifest':
            document_text = "Manifest"
        else:
            document_text = "requested documents"
        
        # Get delivery date if available
        delivery_date = "the scheduled date"
        if trip_order.trip and trip_order.trip.delivery_date:
            delivery_date = trip_order.trip.delivery_date.strftime("%A, %B %d, %Y")
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Trip Completion - {trip_order.vendor.name if trip_order.vendor else 'Order'}</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f8f9fa;
                }}
                .email-container {{
                    background-color: #ffffff;
                    border-radius: 8px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    overflow: hidden;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px 20px;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 24px;
                    font-weight: 600;
                }}
                .content {{
                    padding: 30px 20px;
                }}
                .greeting {{
                    font-size: 18px;
                    margin-bottom: 20px;
                    color: #2c3e50;
                }}
                .action-needed {{
                    background-color: #fff3cd;
                    border: 1px solid #ffeaa7;
                    border-radius: 6px;
                    padding: 20px;
                    margin: 20px 0;
                }}
                .action-needed h3 {{
                    margin: 0 0 10px 0;
                    color: #856404;
                    font-size: 16px;
                }}
                .resources {{
                    background-color: #e8f5e8;
                    border: 1px solid #c3e6c3;
                    border-radius: 6px;
                    padding: 20px;
                    margin: 20px 0;
                }}
                .resources h3 {{
                    margin: 0 0 15px 0;
                    color: #155724;
                    font-size: 16px;
                }}
                .resource-item {{
                    margin: 15px 0;
                    padding: 15px;
                    background-color: white;
                    border-radius: 4px;
                    border-left: 3px solid #28a745;
                }}
                .resource-item h4 {{
                    margin: 0 0 8px 0;
                    color: #155724;
                    font-size: 14px;
                }}
                .resource-item p {{
                    margin: 0;
                    font-size: 14px;
                    color: #666;
                }}
                .attachments {{
                    background-color: #e3f2fd;
                    border: 1px solid #bbdefb;
                    border-radius: 6px;
                    padding: 20px;
                    margin: 20px 0;
                }}
                .attachments h3 {{
                    margin: 0 0 10px 0;
                    color: #1565c0;
                    font-size: 16px;
                }}
                .footer {{
                    background-color: #f8f9fa;
                    padding: 20px;
                    text-align: center;
                    border-top: 1px solid #e9ecef;
                }}
                .footer p {{
                    margin: 5px 0;
                    font-size: 14px;
                    color: #6c757d;
                }}
                .contact-info {{
                    margin-top: 15px;
                    padding-top: 15px;
                    border-top: 1px solid #e9ecef;
                }}
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    <h1>🚚 Delivery Confirmation</h1>
                </div>
                
                <div class="content">
                    <div class="greeting">
                        <p>Hello!</p>
                    </div>
                    
                    <p>This is a friendly reminder that we'll be making a delivery to your dispensary location on <strong>{delivery_date}</strong>.</p>
                    <div class="attachments">
                        <h3>📎 Attached Documents</h3>
                        <p>Please find attached the <strong>{document_text}</strong> detailing the products scheduled for delivery.</p>
                    </div>
                    
                    <div class="action-needed">
                        <h3>⚠️ Action Needed</h3>
                        <p>Please review the attached files to confirm everything is in order for tomorrow's delivery. Let us know if you spot any discrepancies or have questions.</p>
                    </div>
                    
                    <div class="resources">
                        <h3>📚 Additional Resources</h3>
                        
                        <div class="resource-item">
                            <h4>🔬 COAs (Certificates of Analysis)</h4>
                            <p>Available in your Leaf Trade order. Simply click on "Download Lab Results" to access them.</p>
                        </div>
                        
                        <div class="resource-item">
                            <h4>📱 Marketing Materials</h4>
                            <p>Content for In-Store TVs, Social Media, Email Banners, & more—conveniently available for download here: <a href="https://www.dropbox.com/scl/fo/4pj47aolqnltpctbpaanc/AJCrzfA-gRMp7X3xR8Mi0fY?rlkey=97adz4qw5occc91087oxi7nw5&e=1&st=zc2agjcy&dl=0" style="color: #155724;">Dropbox Link</a></p>
                        </div>
                        
                        <div class="resource-item">
                            <h4>🍃 Menu Descriptions & Images</h4>
                            <p>Menu Descriptions & Images for all products can be found here: <a href="https://docs.google.com/spreadsheets/d/12l4m1UbuDK_NLsQFdeOtS1e_zikNYzbiGNhx800RU7c/edit?usp=sharing" style="color: #155724;">Google Sheets Link</a></p>
                        </div>
                    </div>
                    
                    <p>Looking forward to seeing new Affinity Grow products on your menu! Feel free to reach out if you need assistance.</p>
                </div>
                
                <div class="footer">
                    <p><strong>Best Regards,</strong></p>
                    <p><strong>Affinity Grow</strong></p>
                    
                    <div class="contact-info">
                        <p>Need help? Contact our support team</p>
                        <p>📧 support@affinitygrow.com | 📞 (555) 123-4567</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """