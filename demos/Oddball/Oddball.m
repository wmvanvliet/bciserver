function result = Oddball(device, subject, num_circles, num_crosses, server_port)
% function result = Oddball(device, subject, num_circles, num_crosses, server_port)
%
% Perform Oddball experiment. Connects to the bciserver for data
% recording and analysis.
%
% Parameters:
% device  - String indicating the EEG device to record from
%           (One of: 'emulator', 'emotiv-epoc', 'biosemi-activetwo',
%                    'imec-nl', 'imec-be')
% subject - Name of the subject, used as filename for the BDF output.
% num_circles - Number of circles to show
% num_crosses - Number of crosses to show
% server_port - Port number on which the bciserver is listening. Defaults to
%              9000
%
% Returns:
% image generated by the bciserver, which can be shown through 'imshow'

function wait_for_message(con, message)
    response = strtrim(pnet(con, 'readline'));
    
    if ~strcmpi(response, message)
        sca;
        pnet(con, 'close');
        error('expected message: %s\nresponse: %s\n', message, response);
    end
end

%% Configuration of the experiment

% EEG channels to record from.
if strcmp(device, 'emotiv-epoc')
    targetChannels = 'AF3 AF4 F3 F4';
elseif strcmp(device, 'biosemi-activetwo')
    targetChannels = {'Fz FC1 FC2 Cz CP1 CP2 Pz'};
    referenceChannels = {'EXG1 EXG2'};
else
    targetChannels = {'Fz Cz Pz C3 C4'};
end

% Default values for optional parameters
if nargin < 5
    server_port = 9000;
end

if nargin < 4
    num_crosses = 30;
end

if nargin < 3
    num_circles = 150;
end

% Time (in seconds) a stimulus is displayed on the screen
stimulus_duration = 0.2;

% Time (in seconds) of an entire trial
trial_duration = 0.3;

%% Connect to BCI server
try
    con = pnet('tcpconnect', 'localhost', server_port);
    if con == -1
        error('Could not connect to bciserver');
    end
    
    % Output the available devices and classifiers, just for fun
    pnet(con, 'printf', 'DEVICE GET\r\n');
    fprintf('Available devices: %s\n', pnet(con, 'readline'));
    pnet(con, 'printf', 'CLASSIFIER GET\r\n');
    fprintf('Available classifiers: %s\n', pnet(con, 'readline'));
catch ME
    error('Could not connect to bciserver: %s', ME.message);
end

%% Open EEG device
pnet(con, 'printf', 'DEVICE SET %s\r\n', device);

% Instruct server to keep a BDF file with the data
pnet(con, 'printf', 'DEVICE PARAM SET bdf_file %s.bdf\r\n', subject);

% Set the target channels
if ~strcmp(device, 'emulator')
    pnet(con, 'printf', 'DEVICE PARAM SET target_channels %s\r\n', targetChannels); 
end

% For the BIOSEMI, set reference channels
if strcmp(device, 'biosemi-activetwo')
    pnet(con, 'printf', 'DEVICE PARAM SET reference_channels %s\r\n', referenceChannels);
end

% Open the device
pnet(con, 'printf', 'DEVICE OPEN\r\n');

%% Configure classifier
pnet(con, 'printf', 'CLASSIFIER SET erp-plotter\r\n');
wait_for_message(con, 'MODE PROVIDE "idle"');

% Set bandpass filter to 0.5-15Hz
pnet(con, 'printf', 'CLASSIFIER PARAM SET bandpass 0.5 15\r\n');

% Set ERP window to -0.1 to 1.0 seconds
pnet(con, 'printf', 'CLASSIFIER PARAM SET window -0.1 1.0\r\n');

% Set class labels
pnet(con, 'printf', 'CLASSIFIER PARAM SET cl_lab "circle" "cross"\r\n');

%% Open window
if numel( Screen('Screens') ) == 1
    window = Screen('OpenWindow', 0, 0);
else
    window = Screen('OpenWindow', max( Screen('Screens') ), 0);
end

% Get size of the screen, configure the appearance
[window_width, window_height] = Screen('WindowSize', window);
black = BlackIndex(window);
Screen('TextFont', window, 'Cambria');
Screen('TextSize', window, 50);
HideCursor();

%% Load stimuli
circle = Screen('MakeTexture', window, imread('circle.png'));
cross = Screen('MakeTexture', window, imread('cross.png'));

% Figure out position in the center of the screen
stimulus_height = min(window_height - 200, 400);
stimulus_width = stimulus_height;
pos = [window_width - stimulus_width, window_height - stimulus_height, ...
       window_width + stimulus_width, window_height + stimulus_height] ./ 2;
   
%% Begin data recording
WaitSecs(0.1);
pnet(con, 'printf', 'MODE SET data-collect\r\n');
wait_for_message(con, 'MODE PROVIDE "data-collect"');

%% Present stimuli
Screen('FillRect', window, black);
Screen('Flip', window);
WaitSecs(1.0);

% Create a list of stimuli to display
sequence = [ones(1, num_circles) 2*ones(1, num_crosses)];

% Randomize the list
rand_idx = randperm(length(sequence));
sequence = sequence(rand_idx);

% Present each stimulus in the sequence
for i = sequence
     trial_start = GetSecs();
     
	 % Draw the stimulus
     if i == 1
        Screen('DrawTexture', window, circle, [], pos);
     else
        Screen('DrawTexture', window, cross, [], pos);
     end
     
     [~, ~, flip_time] = Screen('Flip', window);

	 % Mark the time the card was shown (the generated data label is retrieved later)
     pnet(con, 'printf', 'MARKER trigger %d\r\n', i);
     
	 % Wait until it is time to blank the screen
     WaitSecs(stimulus_duration);
     
	 % Blank the screen
     Screen('FillRect', window, black);
     Screen('Flip', window);
     
	 % Wait until end of trial
     WaitSecs('UntilTime', trial_start + trial_duration);
end

% Wait a little past the last trial
WaitSecs(2.0);

% Train classifier and obtain result
pnet(con, 'printf', 'MODE SET training\r\n');
wait_for_message(con, 'MODE PROVIDE "training"');

fprintf('Training...\n');

% Read a maximum of 8MB of data for the result plot
% Result comes in the form of:
%     RESULT PROVIDE "training-result" "...base64 encoded PNG file..." 
result = strtrim(pnet(con, 'readline', 2^20));

% Extract and decode the base64 encoded result
result = strsplit(' ', result);
bin = uint8(base64decode(substr(result{4}, 1, length(result{4})-1)));
clear result;

% Write result to a temporary file and load as image
tempfile = sprintf('%s.png', tempname);
fid = fopen(tempfile, 'w');
fwrite(fid, bin, 'uint8');
fclose(fid);
clear bin;
result = imread(tempfile);

% Classifier should be in idle mode by now
wait_for_message(con, 'MODE PROVIDE "idle"');

%% Cleanup
Screen('CloseAll');
pnet(con, 'close');

%% Plot result image
imshow(result);

end