import unittest
from unittest.mock import Mock, patch
import flutter_interceptor as f

class StartupCleanupTests(unittest.TestCase):
    def test_proxy_only_does_not_attach_frida(self):
        api=f.Api(); api.serial='phone'; api.opts={'mode':'proxy'}
        api._device_ready=Mock(return_value=True)
        api._app_pid=Mock(return_value=123)
        api._setup_routing=Mock(return_value=True)
        api._start_mitm=Mock(); api._mitm=Mock()
        api._install_app_ca=Mock(return_value=True)
        api.ensure_frida=Mock(); api._inject=Mock()
        with patch.object(f,'sush',return_value='uid=0(root)'),patch.object(f.threading,'Thread'):
            api._run('test.app')
        self.assertTrue(api.running)
        api.ensure_frida.assert_not_called()
        api._inject.assert_not_called()
        api._install_app_ca.assert_called_once_with(123)

    def test_app_ca_tracks_mount_and_removes_in_same_namespace(self):
        api=f.Api(); api.serial='phone'; api._mitm=Mock()
        api._mitm_ca_name='f2f4540b.0'
        with patch.object(f,'sush_script',side_effect=[
                'FI_CA_MOUNT:/apex/com.android.conscrypt/cacerts:mnt:[123]\nFI_CA_APP_OK\n',
                'FI_CA_REMOVED\n']) as root:
            self.assertTrue(api._install_app_ca(456))
            self.assertEqual(api._ca_overlay[1],456)
            api._remove_app_ca()
            self.assertIsNone(api._ca_overlay)
            self.assertIn('mnt:[123]',root.call_args.args[0])

    def test_failed_app_ca_mount_does_not_report_success(self):
        api=f.Api(); api.serial='phone'; api._mitm=Mock()
        api._mitm_ca_name='f2f4540b.0'; api.log=Mock()
        with patch.object(f,'sush_script',return_value='FI_CA_SHARED_NAMESPACE\n'):
            self.assertFalse(api._install_app_ca(456))
        self.assertIsNone(api._ca_overlay)
        self.assertIn('overlay failed',api.log.call_args.args[0])

    def test_failed_startup_restores_routing(self):
        api=f.Api()
        api.uid='10366'
        api._mitm=Mock()
        api._teardown=Mock()
        self.assertFalse(api._reset())
        api._teardown.assert_called_once()
        self.assertFalse(api.want_running)
        self.assertFalse(api.running)

    def test_attach_failure_releases_suspended_spawn(self):
        api=f.Api()
        dev=Mock()
        dev.spawn.return_value=123
        dev.attach.side_effect=RuntimeError('agent connection closed unexpectedly')
        api.serial='phone'
        api._fdev=dev
        api.opts={'mode':'spawn'}
        with patch.object(f,'frida',Mock(ProcessNotFoundError=type('MissingProcess',(Exception,),{}))),patch.object(f,'adb',return_value=''):
            with self.assertRaisesRegex(RuntimeError,'agent connection closed'):
                api._inject('test.app')
        dev.resume.assert_called_once_with(123)

    def test_dead_attach_process_reports_actionable_error(self):
        api=f.Api()
        dev=Mock()
        api.serial='phone'
        api._fdev=dev
        api.opts={'mode':'attach'}
        api._app_pid=Mock(return_value=123)
        dev.attach.side_effect=f.load_frida().ProcessNotFoundError('process not found')
        with self.assertRaisesRegex(RuntimeError,'exited before Frida could attach'):
            api._inject('test.app')
        dev.attach.assert_called_once_with(123)

if __name__=='__main__': unittest.main()
