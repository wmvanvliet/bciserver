function outImage = resizeImage( inImage, newImageSize, aaKernel )
    
    if numel( newImageSize ) == 1,
        newImageSize = newImageSize * [ size( inImage, 1 ) size( inImage, 2 ) ];
    end
    
    if ( size( inImage, 1 ) ~= newImageSize(1) ) || ( size( inImage, 2 ) ~= newImageSize(2) )

        inClass = class( inImage );
        inImage = cast( inImage, 'double' );
        nLayers = size( inImage, 3 );        

        if (nargin < 3) || ( (nargin >= 3) && ( numel( aaKernel ) == 1 && aaKernel ~= 0 ) )
            if (nargin < 3) || ( isscalar( aaKernel ) && aaKernel < 2 ),
                aaKernel = [.2 1 3 1 .2]; %[0.1915 0.3472 0.5515 0.7676 0.9360 1.0000 0.9360 0.7676 0.5515 0.3472 0.1915];
            else
                if isscalar( aaKernel ),
                    aaKernel = getGaussianKernel( [1 ceil(aaKernel)] );
                elseif ( numel( aaKernel ) == 2 ) && ( aaKernel(1) > 0 && aaKernel(2) > 0 && prod( aaKernel ) > 1 && all( round( aaKernel ) == aaKernel )),
                    aaKernel = getGaussianKernel( aaKernel );
                end
            end
            
            aaKernel = aaKernel / sum( aaKernel(:) );
            for iLayer = 1:nLayers,
                if isvector( aaKernel ),
                    inImage(:,:,iLayer) = filter2( aaKernel, filter2( aaKernel', inImage(:,:,iLayer) ) );
                else
                    inImage(:,:,iLayer) = filter2( aaKernel, inImage(:,:,iLayer) );
                end
            end
        end
        
        outImage = zeros( newImageSize(1), newImageSize(2), nLayers );
        [outMeshX outMeshY] = meshgrid( linspace( 1, size( inImage, 2 ), newImageSize(2) ), ...
                                        linspace( 1, size( inImage, 1 ), newImageSize(1) ) );
        for iLayer = 1:nLayers,
            outImage(:,:,iLayer) = interp2( inImage(:,:,iLayer), outMeshX, outMeshY, '*linear' );
        end
        
        outImage = cast( outImage, inClass );
    else
        outImage = inImage;
    end
    
end % of function RESIZEIMAGE

%---------------------------------------------------------------------
function kernel = getGaussianKernel( kernelDimList, std )
    
    if nargin == 0,
        kernelDimList = 11;
    end
    if numel( kernelDimList ) == 1,
        kernelDimList = [1 kernelDimList];
    end
    if nargin < 2,
        std = max( kernelDimList(:) ) / 4;
    end
    kerDimHalves = (kernelDimList-1) / 2;    
    [x, y] = meshgrid( -kerDimHalves(2):kerDimHalves(2), -kerDimHalves(1):kerDimHalves(1) );
    kernel = exp( -(x.*x + y.*y) / (2*std*std) );
    kernel( kernel < eps*max( kernel(:) ) ) = 0;
    kernelSum = sum( kernel(:) );
    if kernelSum ~= 0,
        kernel = kernel / kernelSum;
    end
    
end % of function GETGAUSSIANKERNEL