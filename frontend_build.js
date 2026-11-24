const { exec } = require('child_process');
exec('npm run build', { cwd: 'C:\\Users\\HARIS\\Desktop\\SecureFed-IDS\\web/frontend' }, (error, stdout, stderr) => {
  console.log('STDOUT:', stdout);
  console.log('STDERR:', stderr);
  if (error) console.log('ERROR:', error);
});