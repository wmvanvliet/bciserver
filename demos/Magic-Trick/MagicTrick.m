function result = MagicTrick(device, subject, num_repetitions, server_port)
% function result = MagicTrick(device, subject, num_repetitions, server_port)
%
% Perform the Magic-Trick experiment. Connects to the bciserver for data
% recording and analysis.
%
% Parameters:
% device  - String indicating the EEG device to record from
%           (One of: 'emulator', 'emotiv-epoc', 'biosemi-activetwo',
%                    'imec-nl', 'imec-be')
% subject - Name of the subject, used as filename for the BDF output.
% num_repetitions - Number of times each cars is presented to the user. To
%                   obtain a good P300 response, use 20 or more. Defaults
%                   to 30.
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
if nargin < 4
    server_port = 9000;
end

if nargin < 3
    num_repetitions = 30;
end

% Time (in seconds) the card is displayed on the screen
stimulus_duration = 0.1;

% Time (in seconds) of the entire trial
trial_duration = 0.5;

%% Connect to BCI server
try
    con = pnet('tcpconnect', 'localhost', server_port);
    if con == -1
        error('Could not connect to bciserver');
    end
    pnet(con, 'printf', 'DEVICE GET\r\n');
    fprintf('Available devices: %s\n', pnet(con, 'readline'));
    pnet(con, 'printf', 'CLASSIFIER GET\r\n');
    fprintf('Available classifiers: %s\n', pnet(con, 'readline'));
catch ME
    error('Could not connect to bciserver: %s', ME.message);
end

%% Open EEG device
pnet(con, 'printf', 'DEVICE SET %s\r\n', device);
pnet(con, 'printf', 'DEVICE PARAM SET bdf_file %s.bdf\r\n', subject);

if ~strcmp(device, 'emulator')
    pnet(con, 'printf', 'DEVICE PARAM SET target_channels %s\r\n', targetChannels); 
end
if strcmp(device, 'biosemi-activetwo')
    pnet(con, 'printf', 'DEVICE PARAM SET reference_channels %s\r\n', referenceChannels);
end

pnet(con, 'printf', 'DEVICE OPEN\r\n');

%% Configure classifier
pnet(con, 'printf', 'CLASSIFIER SET erp-plotter\r\n');
wait_for_message(con, 'MODE PROVIDE "idle"');

% Set bandpass filter to 0.5-15Hz
pnet(con, 'printf', 'CLASSIFIER PARAM SET bandpass 0.5 15\r\n');

% Set ERP window to -0.1 to 1.0 seconds
pnet(con, 'printf', 'CLASSIFIER PARAM SET window -0.1 1.0\r\n');

% Set class labels
pnet(con, 'printf', ['CLASSIFIER PARAM SET cl_lab ', ...
   '"Ace of spades" ', ...
   '"Jack of clubs" ', ...
   '"Queen of hearts" ', ...
   '"King of diamonds" ', ...
   '"10 of spaces" ', ...
   '"3 of clubs" ', ...
   '"10 of hearts" ', ...
   '"3 of diamonds" ', ...
   '"King of spades"\r\n']);

%% Open window
if numel( Screen('Screens') ) == 1
    window = Screen('OpenWindow', 0, 0);
else
    window = Screen('OpenWindow', max( Screen('Screens') ), 0);
end

% Get size of the screen, configure the appearance
[window_width, window_height] = Screen('WindowSize', window);
black = BlackIndex(window);
white = WhiteIndex(window);
Screen('TextFont', window, 'Cambria');
Screen('TextSize', window, 50);
HideCursor();

%% Load card images
stimuli = zeros(1, 9);
stimuli(1) = Screen('MakeTexture', window, imread('cards/s_a.png'));
stimuli(2) = Screen('MakeTexture', window, imread('cards/c_j.png'));
stimuli(3) = Screen('MakeTexture', window, imread('cards/h_q.png'));
stimuli(4) = Screen('MakeTexture', window, imread('cards/d_k.png'));
stimuli(5) = Screen('MakeTexture', window, imread('cards/s_10.png'));
stimuli(6) = Screen('MakeTexture', window, imread('cards/c_03.png'));
stimuli(7) = Screen('MakeTexture', window, imread('cards/h_10.png'));
stimuli(8) = Screen('MakeTexture', window, imread('cards/d_03.png'));
stimuli(9) = Screen('MakeTexture', window, imread('cards/s_k.png'));

          
% Determine position on screen where to display the cards
stimulus_height = min(window_height - 200, 400);
stimulus_width = (stimulus_height / 1433) * 929;
pos = [window_width - stimulus_width, window_height - stimulus_height, ...
       window_width + stimulus_width, window_height + stimulus_height] ./ 2;

%% Show possible cards for the player to pick
Screen('FillRect', window, black);
DrawFormattedText(window, 'Pick a card...', 'center', 10, white);

small_height = (window_height - 200) / 3 - 10;
small_width = (small_height / 1433) * 929;

total_width = 3*small_width + 2*10;
total_height = 3*small_height + 2*10;

for i = 1:3
    for j = 1:3
        x = (window_width-total_width)/2 + (i-1)*(small_width+10);
        y = 100 + (window_height-total_height)/2 + (j-1)*(small_height+10);
        small_pos = [x, y, x+small_width, y+small_height];
        Screen('DrawTexture', window, stimuli((i-1)*3+j), [], small_pos);
    end
end

Screen('Flip', window);
WaitSecs(10.0);

%% Begin data recording
WaitSecs(0.1);
pnet(con, 'printf', 'MODE SET data-collect\r\n');
wait_for_message(con, 'MODE PROVIDE "data-collect"');

%% Present stimuli
Screen('FillRect', window, black);
Screen('Flip', window);
WaitSecs(1.0);

% Create a list of cards to display, taking the number of repetitions into account
sequence = zeros(1, length(stimuli)*num_repetitions);

% Randomize the list, making sure no 2 stimuli are repeated after eachother
for i = 0:num_repetitions-1
    rand_idx = randperm(length(stimuli));
    
    % Check for a stimulus that occurs twice in a row
    if i > 0 && sequence(i) == rand_idx(1)
        % Reverse the random order of the stimuli
        rand_idx = rand_idx(end:-1:1);
    end
    
    sequence(i*length(stimuli)+1:(i+1)*length(stimuli)) = rand_idx;
end

% Present each card in the sequence
for i = sequence
     trial_start = GetSecs();
     
	 % Draw the card
     Screen('DrawTexture', window, stimuli(i), [], pos);
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